import asyncio
import uuid
from collections import defaultdict
from typing import Any

from postgrest.exceptions import APIError
from pydantic import ValidationError
from supabase import AsyncClient

from ai.schemas.enums import ActivityType
from app.core.errors import NotFoundError
from app.ingestion.adapters import AdaptedLead, JsonLeadAdapter, record_errors
from app.models import Lead
from app.repositories.activity import ActivityRepository
from app.repositories.business import BusinessRepository
from app.repositories.lead import LeadRepository
from app.schemas.activity import ActivityRead
from app.schemas.common import Page, RecordError
from app.schemas.lead import LeadCreate, LeadListParams, LeadSummary, LeadUpdate
from app.schemas.lead_import import ImportEnvelope, ImportOutcome, ImportRecordResult, ImportResult
from app.services.business import require_business

# PostgreSQL SQLSTATE class 23: integrity constraint violation (unique, check, foreign key, not null).
_INTEGRITY_ERROR_CLASS = "23"

# Serializes lead writes per business (match-then-save deduplication must not interleave). In-process only: run
# a single backend process, or move matching into the database before scaling out.
_business_locks: defaultdict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)


def _activity(activity_type: ActivityType, description: str, metadata: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"activity_type": activity_type, "description": description, "metadata": metadata} | extra


class LeadService:
    def __init__(self, db: AsyncClient) -> None:
        self.leads = LeadRepository(db)
        self.businesses = BusinessRepository(db)
        self.activities = ActivityRepository(db)

    async def get(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> Lead:
        await require_business(self.businesses, business_id)
        lead = await self.leads.get(business_id, lead_id)
        if lead is None:
            raise NotFoundError(f"Lead {lead_id} not found")
        return lead

    async def list(self, business_id: uuid.UUID, params: LeadListParams) -> Page[LeadSummary]:
        await require_business(self.businesses, business_id)
        leads, total = await self.leads.list_page(business_id, params)
        return Page(items=leads, total=total, limit=params.limit, offset=params.offset)

    async def timeline(self, business_id: uuid.UUID, lead_id: uuid.UUID, limit: int, offset: int) -> Page[ActivityRead]:
        await self.get(business_id, lead_id)
        rows, total = await self.activities.list_for_lead(business_id, lead_id, limit, offset)
        return Page(items=[ActivityRead.model_validate(row) for row in rows], total=total, limit=limit, offset=offset)

    async def create(self, business_id: uuid.UUID, data: LeadCreate) -> Lead:
        await require_business(self.businesses, business_id)
        async with _business_locks[business_id]:
            lead, _ = await self._upsert(business_id, data)
        return lead

    async def update(self, business_id: uuid.UUID, lead_id: uuid.UUID, data: LeadUpdate) -> Lead:
        async with _business_locks[business_id]:
            lead = await self.get(business_id, lead_id)
            return await self._apply(lead, data.model_dump(exclude_unset=True)) or lead

    async def _match(self, business_id: uuid.UUID, data: LeadCreate) -> Lead | None:
        if data.external_id:
            match = await self.leads.get_by_external_id(business_id, data.source, data.external_id)
            if match is not None:
                return match
        if data.email:
            match = await self.leads.get_oldest_by_email(business_id, data.email)
            if match is not None:
                return match
        if data.phone:
            return await self.leads.get_oldest_by_phone(business_id, data.phone)
        return None

    async def _upsert(
        self,
        business_id: uuid.UUID,
        data: LeadCreate,
        adapted: AdaptedLead | None = None,
    ) -> tuple[Lead, ImportOutcome]:
        lead = await self._match(business_id, data)
        values = data.model_dump(exclude_none=True)
        if adapted:
            values["raw_payload"] = adapted.raw_payload
        if lead is None:
            metadata = (
                {}
                if adapted is None
                else {
                    "imported": True,
                    "contact_attempts": adapted.history.contact_attempts,
                    "replied": adapted.history.replied,
                }
            )
            created = _activity(
                ActivityType.LEAD_CREATED,
                "Lead imported" if adapted else "Lead created",
                metadata,
                channel=adapted.history.preferred_channel if adapted else None,
            )
            return await self.leads.save(business_id, None, values, [created]), ImportOutcome.CREATED
        # Preserve the original source identity and timestamp on contact matches.
        for field in ("source", "external_id", "created_at"):
            values.pop(field, None)
        values["custom_fields"] = lead.custom_fields | data.custom_fields
        updated = await self._apply(lead, values)
        return (updated, ImportOutcome.UPDATED) if updated else (lead, ImportOutcome.SKIPPED)

    async def _apply(self, lead: Lead, values: dict[str, Any]) -> Lead | None:
        """Save the values that differ from ``lead`` with their activities; the saved lead, or None if unchanged."""
        changes = {key: value for key, value in values.items() if getattr(lead, key) != value}
        if not changes:
            return None
        events = [_activity(ActivityType.LEAD_UPDATED, "Lead updated", {"fields": sorted(changes)})]
        for field, kind in (("status", ActivityType.STATUS_CHANGED), ("lead_score", ActivityType.SCORE_CHANGED)):
            if field in changes:
                description = f"{field.replace('_', ' ').title()} changed"
                events.append(_activity(kind, description, {"from": getattr(lead, field), "to": changes[field]}))
        return await self.leads.save(lead.business_id, lead.id, changes, events)

    async def import_batch(self, business_id: uuid.UUID, envelope: ImportEnvelope) -> ImportResult:
        """Each record is saved on its own (one transaction per record), so one bad record never undoes the rest."""
        await require_business(self.businesses, business_id)
        async with _business_locks[business_id]:
            return await self._import_records(business_id, envelope)

    async def _import_records(self, business_id: uuid.UUID, envelope: ImportEnvelope) -> ImportResult:
        results = []
        adapter = JsonLeadAdapter()
        for index, record in enumerate(envelope.leads):
            external_id = record.get("lead_id")
            result = ImportRecordResult(
                index=index,
                external_id=external_id if isinstance(external_id, str) else None,
                outcome=ImportOutcome.FAILED,
            )
            try:
                adapted = await adapter.parse(record)
                lead, outcome = await self._upsert(business_id, adapted.data, adapted)
                result.lead_id, result.outcome = lead.id, outcome
            except ValidationError as exc:
                result.errors = record_errors(exc)
            except APIError as exc:
                if not (exc.code or "").startswith(_INTEGRITY_ERROR_CLASS):
                    raise
                result.errors = [
                    RecordError(loc=[], msg="Record violates a database constraint", type="integrity_error")
                ]
            results.append(result)
        return ImportResult.from_results(results)

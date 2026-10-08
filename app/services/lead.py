from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from postgrest.exceptions import APIError
from pydantic import ValidationError
from supabase import AsyncClient

from ai.schemas.enums import ActivityType
from app.core.errors import NotFoundError, UnprocessableError
from app.ingestion.adapters import AdaptedLead, JsonLeadAdapter, record_errors
from app.intelligence import (
    Event,
    ScoreBreakdown,
    custom_field_errors,
    lead_facts,
    next_follow_up,
    priority_for,
    score_lead,
    upstream_ai_score,
)
from app.models import Activity, Lead
from app.repositories.activity import ActivityRepository
from app.repositories.business import BusinessRepository
from app.repositories.lead import LeadRepository
from app.schemas.activity import ActivityRead
from app.schemas.common import Page, RecordError
from app.schemas.lead import (
    LeadCreate,
    LeadListItem,
    LeadListParams,
    LeadRead,
    LeadSummary,
    LeadUpdate,
    RescoreResult,
)
from app.schemas.lead_import import ImportEnvelope, ImportOutcome, ImportRecordResult, ImportResult
from app.services.business import BusinessSettings, require_business

# PostgreSQL SQLSTATE class 23: integrity constraint violation (unique, check, foreign key, not null).
_INTEGRITY_ERROR_CLASS = "23"

# Serializes lead writes per business (match-then-save deduplication must not interleave). In-process only: run
# a single backend process, or move matching into the database before scaling out.
_business_locks: defaultdict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)

# Derived by the service on every write; never taken from client or import input.
_DERIVED_FIELDS = frozenset({"lead_score"})


class InvalidCustomFields(UnprocessableError):
    def __init__(self, errors: list[RecordError]) -> None:
        message = "; ".join(f"{error.loc[-1]}: {error.msg}" for error in errors)
        super().__init__(message, details=[error.model_dump() for error in errors])
        self.errors = errors


def _activity(activity_type: ActivityType, description: str, metadata: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"activity_type": activity_type, "description": description, "metadata": metadata} | extra


def _events(activities: list[Activity]) -> list[Event]:
    return [Event(a.activity_type, a.created_at, a.metadata) for a in activities]


def _score_changed(previous: int | None, breakdown: ScoreBreakdown) -> dict[str, Any]:
    """The ``score_changed`` activity: enough to answer "why did this score change?" later."""
    metadata = {
        "from": previous,
        "to": breakdown.final,
        "deterministic": breakdown.deterministic,
        "ai": breakdown.ai,
        "rules": [rule.id for rule in breakdown.matched],
    }
    return _activity(ActivityType.SCORE_CHANGED, "Lead score changed", metadata)


class LeadService:
    def __init__(self, db: AsyncClient, now: datetime) -> None:
        self.leads = LeadRepository(db)
        self.businesses = BusinessRepository(db)
        self.activities = ActivityRepository(db)
        self.now = now
        self._settings: dict[uuid.UUID, BusinessSettings] = {}

    async def settings(self, business_id: uuid.UUID) -> BusinessSettings:
        """The business's parsed settings, or ``NotFoundError``. Loaded once per service (one request)."""
        if business_id not in self._settings:
            self._settings[business_id] = BusinessSettings.of(await require_business(self.businesses, business_id))
        return self._settings[business_id]

    async def get(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> Lead:
        await self.settings(business_id)
        lead = await self.leads.get(business_id, lead_id)
        if lead is None:
            raise NotFoundError(f"Lead {lead_id} not found")
        return lead

    async def read(self, lead: Lead) -> LeadRead:
        """The API view of a lead, with its next follow-up."""
        settings = await self.settings(lead.business_id)
        follow_up = next_follow_up(settings.configuration, lead, self.now)
        return LeadRead.model_validate(lead.model_dump() | {"follow_up": follow_up})

    async def list(self, business_id: uuid.UUID, params: LeadListParams) -> Page[LeadListItem]:
        settings = await self.settings(business_id)
        leads, total = await self.leads.list_page(business_id, params)
        items = [self._list_item(settings, lead) for lead in leads]
        return Page(items=items, total=total, limit=params.limit, offset=params.offset)

    def _list_item(self, settings: BusinessSettings, lead: LeadSummary) -> LeadListItem:
        follow_up = next_follow_up(settings.configuration, lead, self.now)
        return LeadListItem.model_validate(lead.model_dump() | {"follow_up": follow_up})

    async def timeline(self, business_id: uuid.UUID, lead_id: uuid.UUID, limit: int, offset: int) -> Page[ActivityRead]:
        await self.get(business_id, lead_id)
        rows, total = await self.activities.list_for_lead(business_id, lead_id, limit, offset)
        return Page(items=[ActivityRead.model_validate(row) for row in rows], total=total, limit=limit, offset=offset)

    async def score(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> ScoreBreakdown:
        """How the lead scores now (the stored score may predate a settings change or the passing of time)."""
        lead = await self.get(business_id, lead_id)
        activities = await self.activities.all_for_lead(business_id, lead_id)
        return self._breakdown(await self.settings(business_id), lead, _events(activities))

    async def create(self, business_id: uuid.UUID, data: LeadCreate) -> Lead:
        settings = await self.settings(business_id)
        async with _business_locks[business_id]:
            lead, _ = await self._upsert(settings, business_id, data)
        return lead

    async def update(self, business_id: uuid.UUID, lead_id: uuid.UUID, data: LeadUpdate) -> Lead:
        settings = await self.settings(business_id)
        values = data.model_dump(exclude_unset=True)
        self._check_custom_fields(settings, values.get("custom_fields", {}))
        async with _business_locks[business_id]:
            lead = await self.get(business_id, lead_id)
            return await self._apply(settings, lead, values) or lead

    async def rescore(self, business_id: uuid.UUID) -> RescoreResult:
        """Recompute every lead's score and priority, e.g. after the scoring settings changed."""
        settings = await self.settings(business_id)
        async with _business_locks[business_id]:
            leads, activities = await asyncio.gather(
                self.leads.list_full(business_id), self.activities.all_for_business(business_id)
            )
            by_lead: defaultdict[uuid.UUID, list[Activity]] = defaultdict(list)
            for activity in activities:
                by_lead[activity.lead_id].append(activity)
            changed = 0
            for lead in leads:
                if await self._apply(settings, lead, {}, _events(by_lead[lead.id])):
                    changed += 1
        return RescoreResult(total=len(leads), changed=changed)

    def _check_custom_fields(self, settings: BusinessSettings, custom_fields: dict[str, Any]) -> None:
        if errors := custom_field_errors(settings.custom_fields, custom_fields):
            raise InvalidCustomFields(errors)

    def _breakdown(self, settings: BusinessSettings, lead: Lead, events: Sequence[Event]) -> ScoreBreakdown:
        facts = lead_facts(lead, events, self.now)
        return score_lead(settings.configuration.scoring, facts, lead.custom_fields, upstream_ai_score(lead))

    def _derive(
        self, settings: BusinessSettings, lead: Lead, values: dict[str, Any], events: Sequence[Event]
    ) -> tuple[dict[str, Any], ScoreBreakdown]:
        """``values`` plus the derived score, and the priority unless the input set one.

        A computed priority replaces the stored one only when the score changes (or there is none), so a priority
        a user picked survives edits that do not move the score.
        """
        values = {key: value for key, value in values.items() if key not in _DERIVED_FIELDS}
        breakdown = self._breakdown(settings, lead.model_copy(update=values), events)
        derived = values | {"lead_score": breakdown.final}
        if "priority" not in values and (breakdown.final != lead.lead_score or lead.priority is None):
            derived["priority"] = priority_for(breakdown.final, settings.configuration.priority)
        return derived, breakdown

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
        settings: BusinessSettings,
        business_id: uuid.UUID,
        data: LeadCreate,
        adapted: AdaptedLead | None = None,
    ) -> tuple[Lead, ImportOutcome]:
        self._check_custom_fields(settings, data.custom_fields)
        lead = await self._match(business_id, data)
        values = data.model_dump(exclude_none=True)
        if adapted:
            values["raw_payload"] = adapted.raw_payload
        if lead is None:
            return await self._insert(settings, business_id, values, adapted), ImportOutcome.CREATED
        # Preserve the original source identity and timestamp on contact matches.
        for field in ("source", "external_id", "created_at"):
            values.pop(field, None)
        values["custom_fields"] = lead.custom_fields | data.custom_fields
        updated = await self._apply(settings, lead, values)
        return (updated, ImportOutcome.UPDATED) if updated else (lead, ImportOutcome.SKIPPED)

    async def _insert(
        self, settings: BusinessSettings, business_id: uuid.UUID, values: dict[str, Any], adapted: AdaptedLead | None
    ) -> Lead:
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
        # The row as it will be stored, so facts see the same defaults the database applies.
        draft = Lead.model_validate(
            {
                "id": uuid.UUID(int=0),
                "business_id": business_id,
                "external_id": None,
                "status": "new",
                "priority": None,
                "first_name": None,
                "last_name": None,
                "email": None,
                "phone": None,
                "company_name": None,
                "notes": None,
                "lead_score": None,
                "sentiment": None,
                "ai_summary": None,
                "recommended_action": None,
                "custom_fields": {},
                "raw_payload": {},
                "last_contact_at": None,
                "created_at": self.now,
                "updated_at": self.now,
            }
            | values
        )
        derived, breakdown = self._derive(
            settings, draft, values, [Event(ActivityType.LEAD_CREATED, draft.created_at, metadata)]
        )
        return await self.leads.save(business_id, None, derived, [created, _score_changed(None, breakdown)])

    async def _apply(
        self, settings: BusinessSettings, lead: Lead, values: dict[str, Any], events: Sequence[Event] | None = None
    ) -> Lead | None:
        """Save the values (plus derived score and priority) that differ from ``lead``, with their activities.

        The saved lead, or None if nothing changed. ``events`` are the lead's activities when already loaded.
        """
        if events is None:
            events = _events(await self.activities.all_for_lead(lead.business_id, lead.id))
        derived, breakdown = self._derive(settings, lead, values, events)
        changes = {key: value for key, value in derived.items() if getattr(lead, key) != value}
        if not changes:
            return None
        activities = []
        if set(changes) - {"lead_score", "priority"}:
            activities.append(_activity(ActivityType.LEAD_UPDATED, "Lead updated", {"fields": sorted(changes)}))
        if "status" in changes:
            metadata = {"from": lead.status, "to": changes["status"]}
            activities.append(_activity(ActivityType.STATUS_CHANGED, "Status changed", metadata))
        if "lead_score" in changes:
            activities.append(_score_changed(lead.lead_score, breakdown))
        elif "priority" in changes and not activities:
            activities.append(_activity(ActivityType.LEAD_UPDATED, "Lead updated", {"fields": ["priority"]}))
        return await self.leads.save(lead.business_id, lead.id, changes, activities)

    async def import_batch(self, business_id: uuid.UUID, envelope: ImportEnvelope) -> ImportResult:
        """Each record is saved on its own (one transaction per record), so one bad record never undoes the rest."""
        settings = await self.settings(business_id)
        async with _business_locks[business_id]:
            return await self._import_records(settings, business_id, envelope)

    async def _import_records(
        self, settings: BusinessSettings, business_id: uuid.UUID, envelope: ImportEnvelope
    ) -> ImportResult:
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
                lead, outcome = await self._upsert(settings, business_id, adapted.data, adapted)
                result.lead_id, result.outcome = lead.id, outcome
            except ValidationError as exc:
                result.errors = record_errors(exc)
            except InvalidCustomFields as exc:
                result.errors = exc.errors
            except APIError as exc:
                if not (exc.code or "").startswith(_INTEGRITY_ERROR_CLASS):
                    raise
                result.errors = [
                    RecordError(loc=[], msg="Record violates a database constraint", type="integrity_error")
                ]
            results.append(result)
        return ImportResult.from_results(results)

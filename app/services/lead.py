import asyncio
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from postgrest.exceptions import APIError
from pydantic import ValidationError
from supabase import AsyncClient

from ai.schemas.enums import ActivityType, Channel
from app.core.errors import NotFoundError, UnprocessableError
from app.core.locks import BusinessLock, DatabaseBusinessLock
from app.core.logger import Logger
from app.ingestion.adapters import AdaptedLead, JsonLeadAdapter, record_errors
from app.ingestion.normalize import to_e164
from app.intelligence import (
    Event,
    ScoreBreakdown,
    ai_score,
    custom_field_errors,
    lead_facts,
    next_follow_up,
    priority_for,
    score_lead,
)
from app.models import Activity, AnalysisJob, AnalysisTrigger, Business, Lead
from app.repositories.activity import ActivityRepository
from app.repositories.analysis_job import AnalysisJobRepository
from app.repositories.business import BusinessRepository
from app.repositories.lead import LeadRepository
from app.schemas.activity import ActivityRead
from app.schemas.analysis import AnalysisJobRead, AnalysisResult, LeadAnalysisState, RunCost, SavedAnalysis
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

logger = Logger(__name__)

# PostgreSQL SQLSTATE class 23: integrity constraint violation (unique, check, foreign key, not null).
_INTEGRITY_ERROR_CLASS = "23"

# Derived by the service on every write; never taken from client or import input.
_DERIVED_FIELDS = frozenset({"lead_score"})


class InvalidCustomFields(UnprocessableError):
    def __init__(self, errors: list[RecordError]) -> None:
        message = "; ".join(f"{error.loc[-1]}: {error.msg}" for error in errors)
        super().__init__(message, details=[error.model_dump() for error in errors])
        self.errors = errors


def _activity(activity_type: ActivityType, description: str, metadata: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"activity_type": activity_type, "description": description, "metadata": metadata} | extra


def _split_name(name: str | None) -> tuple[str | None, str | None]:
    """A profile name as (first, last): ``"Dana Levi"`` -> ``("Dana", "Levi")``; clipped to the column sizes."""
    parts = (name or "").split(maxsplit=1)
    first = parts[0][:100] if parts else None
    last = parts[1][:100] if len(parts) > 1 else None
    return first, last


@dataclass(frozen=True)
class InboundChannelMessage:
    """A message a lead sent on a channel. ``phone`` is E.164 or national (read in the business's country)."""

    channel: Channel
    message_id: str
    phone: str
    sender_name: str | None
    body: str | None
    kind: str
    sent_at: datetime

    @property
    def activity_type(self) -> ActivityType:
        return _RECEIVED[self.channel]

    @property
    def description(self) -> str:
        label = _CHANNEL_LABELS[self.channel]
        return f"{label} message received" if self.kind == "text" else f"{label} {self.kind} received"


@dataclass(frozen=True)
class OutboundChannelMessage:
    channel: Channel
    message_id: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def activity_type(self) -> ActivityType:
        return _SENT[self.channel]

    @property
    def description(self) -> str:
        return f"{_CHANNEL_LABELS[self.channel]} message sent"


_RECEIVED = {Channel.WHATSAPP: ActivityType.WHATSAPP_RECEIVED, Channel.EMAIL: ActivityType.EMAIL_RECEIVED}
_SENT = {Channel.WHATSAPP: ActivityType.WHATSAPP_SENT, Channel.EMAIL: ActivityType.EMAIL_SENT}
_CHANNEL_LABELS = {Channel.WHATSAPP: "WhatsApp", Channel.EMAIL: "Email"}


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
        self.jobs = AnalysisJobRepository(db)
        # Serializes lead writes per business across processes (match-then-save deduplication must not interleave).
        self.lock: BusinessLock = DatabaseBusinessLock(db)
        self.now = now
        self._businesses: dict[uuid.UUID, Business] = {}

    async def business(self, business_id: uuid.UUID) -> Business:
        """The business, or ``NotFoundError``. Loaded once per service (one request)."""
        if business_id not in self._businesses:
            self._businesses[business_id] = await require_business(self.businesses, business_id)
        return self._businesses[business_id]

    async def settings(self, business_id: uuid.UUID) -> BusinessSettings:
        return BusinessSettings.of(await self.business(business_id))

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

    async def request_analysis(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> AnalysisJob:
        """Queue the lead's AI analysis for the worker (MAIN_PLAN §58: AI never runs inside a request).

        Returns the lead's open job: asking again while one is pending or running does not queue a second run.
        """
        await self.get(business_id, lead_id)
        job = await self.jobs.enqueue(business_id, lead_id, AnalysisTrigger.MANUAL)
        logger.fire(
            "lead_analysis_requested", business_id=str(business_id), lead_id=str(lead_id), job_id=str(job.id),
            status=job.status.value,
        )
        return job

    async def analysis_state(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> LeadAnalysisState:
        """The lead's latest job and the latest analysis the AI saved (they differ while a new run is open)."""
        await self.get(business_id, lead_id)
        job = await self.jobs.latest_for_lead(business_id, lead_id)
        latest = await self.activities.latest_of_type(business_id, lead_id, ActivityType.AI_ANALYSIS)
        return LeadAnalysisState(
            job=AnalysisJobRead.model_validate(job.model_dump()) if job else None,
            result=SavedAnalysis.from_activity(latest) if latest else None,
        )

    async def analysis_inputs(
        self, business_id: uuid.UUID, lead_id: uuid.UUID
    ) -> tuple[Business, Lead, Sequence[Activity]]:
        """What the AI reads about the lead: its business, the lead and its timeline."""
        business = await self.business(business_id)
        lead = await self.get(business_id, lead_id)
        return business, lead, await self.activities.all_for_lead(business_id, lead_id)

    async def record_analysis(
        self, business_id: uuid.UUID, lead_id: uuid.UUID, result: AnalysisResult, cost: RunCost | None = None
    ) -> Lead:
        """Save the AI's summary, next action and score (blended into the deterministic score) with an
        ``ai_analysis`` activity. Applied to the lead as it is now: the AI ran outside the business lock.
        """
        metadata: dict[str, Any] = {
            "ai_score": result.ai_score.overall_ai_score,
            "qualified": result.qualification.qualified,
            "recommended_action": result.recommendation.action.value,
            "qualification": result.qualification.model_dump(mode="json"),
            "score": result.ai_score.model_dump(mode="json"),
            "recommendation": result.recommendation.model_dump(mode="json"),
        }
        if cost is not None:
            metadata["cost"] = cost.as_metadata()
        analysis = _activity(ActivityType.AI_ANALYSIS, "AI analysis", metadata)
        values = {"ai_summary": result.qualification.summary, "recommended_action": result.recommendation.action.value}
        settings = await self.settings(business_id)
        async with self.lock.hold(business_id):
            current = await self.get(business_id, lead_id)
            saved = await self._apply(settings, current, values, extra=[analysis]) or current
        logger.fire(
            "lead_analysis_recorded",
            business_id=str(business_id),
            lead_id=str(lead_id),
            ai_score=result.ai_score.overall_ai_score,
            qualified=result.qualification.qualified,
            recommended_action=result.recommendation.action.value,
            lead_score=saved.lead_score,
            priority=saved.priority,
        )
        return saved

    async def create(self, business_id: uuid.UUID, data: LeadCreate) -> Lead:
        settings = await self.settings(business_id)
        async with self.lock.hold(business_id):
            lead, outcome = await self._upsert(settings, business_id, data)
        logger.fire(
            "lead_saved", business_id=str(business_id), lead_id=str(lead.id), outcome=outcome.value, source=data.source
        )
        return lead

    async def update(self, business_id: uuid.UUID, lead_id: uuid.UUID, data: LeadUpdate) -> Lead:
        settings = await self.settings(business_id)
        values = data.model_dump(exclude_unset=True)
        self._check_custom_fields(settings, values.get("custom_fields", {}))
        if values.get("phone"):
            values["phone"] = to_e164(values["phone"], settings.configuration.phone_region)
        async with self.lock.hold(business_id):
            lead = await self.get(business_id, lead_id)
            saved = await self._apply(settings, lead, values)
        logger.fire(
            "lead_updated" if saved else "lead_update_unchanged",
            business_id=str(business_id),
            lead_id=str(lead_id),
            fields=sorted(values),
        )
        return saved or lead

    async def rescore(self, business_id: uuid.UUID) -> RescoreResult:
        """Recompute every lead's score and priority, e.g. after the scoring settings changed."""
        settings = await self.settings(business_id)
        async with self.lock.hold(business_id):
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
        logger.fire("leads_rescored", business_id=str(business_id), total=len(leads), changed=changed)
        return RescoreResult(total=len(leads), changed=changed)

    def _check_custom_fields(self, settings: BusinessSettings, custom_fields: dict[str, Any]) -> None:
        if errors := custom_field_errors(settings.custom_fields, custom_fields):
            logger.fire("custom_fields_invalid", level="warning", fields=sorted({str(e.loc[-1]) for e in errors}))
            raise InvalidCustomFields(errors)

    def _breakdown(self, settings: BusinessSettings, lead: Lead, events: Sequence[Event]) -> ScoreBreakdown:
        facts = lead_facts(lead, events, self.now)
        return score_lead(settings.configuration.scoring, facts, lead.custom_fields, ai_score(lead, events))

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
        if data.phone:
            data = data.model_copy(update={"phone": to_e164(data.phone, settings.configuration.phone_region)})
        lead = await self._match(business_id, data)
        values = data.model_dump(exclude_none=True)
        if adapted:
            values["raw_payload"] = adapted.raw_payload
        if lead is None:
            return await self._insert(settings, business_id, values, adapted), ImportOutcome.CREATED
        # Preserve the original source identity and timestamp on contact matches.
        for key in ("source", "external_id", "created_at"):
            values.pop(key, None)
        values["custom_fields"] = lead.custom_fields | data.custom_fields
        updated = await self._apply(settings, lead, values)
        return (updated, ImportOutcome.UPDATED) if updated else (lead, ImportOutcome.SKIPPED)

    async def _insert(
        self,
        settings: BusinessSettings,
        business_id: uuid.UUID,
        values: dict[str, Any],
        adapted: AdaptedLead | None,
        *,
        channel: Channel | None = None,
        extra: Sequence[dict[str, Any]] = (),
    ) -> Lead:
        """Insert a lead with its creation activity, then ``extra`` activities (e.g. the message that created it)."""
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
            channel=adapted.history.preferred_channel if adapted else channel,
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
        events = [
            Event(ActivityType.LEAD_CREATED, draft.created_at, metadata),
            *(Event(a["activity_type"], draft.created_at, a["metadata"]) for a in extra),
        ]
        derived, breakdown = self._derive(settings, draft, values, events)
        trigger = AnalysisTrigger.LEAD_CREATED if settings.auto_analyze else None
        activities = [created, *extra, _score_changed(None, breakdown)]
        return await self.leads.save(business_id, None, derived, activities, trigger)

    async def receive_message(self, business_id: uuid.UUID, message: InboundChannelMessage) -> tuple[Lead, bool] | None:
        """Record a message a lead sent on a channel: on the lead with that phone, or on a new lead (which queues
        NewLeadFlow like any other). ``(lead, created)``, or None when the message is already recorded.
        """
        settings = await self.settings(business_id)
        received = _activity(
            message.activity_type,
            message.description,
            {"message_id": message.message_id, "body": message.body, "kind": message.kind},
            channel=message.channel,
        )
        phone = to_e164(message.phone, settings.configuration.phone_region)
        async with self.lock.hold(business_id):
            if await self.activities.has_message(business_id, message.message_id):
                return None
            lead = await self.leads.get_oldest_by_phone(business_id, phone)
            if lead is None:
                first_name, last_name = _split_name(message.sender_name)
                values = {
                    "source": message.channel.value,
                    "phone": phone,
                    "first_name": first_name,
                    "last_name": last_name,
                    "notes": message.body,
                    "last_contact_at": message.sent_at,
                }
                values = {key: value for key, value in values.items() if value is not None}
                lead = await self._insert(
                    settings, business_id, values, None, channel=message.channel, extra=[received]
                )
                created = True
            else:
                saved = await self._apply(settings, lead, {"last_contact_at": message.sent_at}, extra=[received])
                lead, created = saved or lead, False
        logger.fire(
            "lead_message_received", business_id=str(business_id), lead_id=str(lead.id), channel=message.channel.value,
            created=created, kind=message.kind,
        )
        return lead, created

    async def record_outbound(
        self, business_id: uuid.UUID, lead_id: uuid.UUID, message: OutboundChannelMessage
    ) -> Lead:
        """Record a message sent to the lead (it counts as a contact for scoring and follow-up timing)."""
        settings = await self.settings(business_id)
        metadata = {"message_id": message.message_id, "body": message.body} | message.metadata
        sent = _activity(message.activity_type, message.description, metadata, channel=message.channel)
        async with self.lock.hold(business_id):
            lead = await self.get(business_id, lead_id)
            saved = await self._apply(settings, lead, {"last_contact_at": self.now}, extra=[sent]) or lead
        logger.fire(
            "lead_message_sent", business_id=str(business_id), lead_id=str(lead_id), channel=message.channel.value
        )
        return saved

    async def _apply(
        self,
        settings: BusinessSettings,
        lead: Lead,
        values: dict[str, Any],
        events: Sequence[Event] | None = None,
        extra: Sequence[dict[str, Any]] = (),
    ) -> Lead | None:
        """Save the values (plus derived score and priority) that differ from ``lead``, with their activities.

        The saved lead, or None if nothing changed and there is no ``extra`` activity to record (``extra`` is
        written first and counts for the score). ``events`` are the lead's activities when already loaded.
        """
        if events is None:
            events = _events(await self.activities.all_for_lead(lead.business_id, lead.id))
        events = [*events, *(Event(a["activity_type"], self.now, a["metadata"]) for a in extra)]
        derived, breakdown = self._derive(settings, lead, values, events)
        changes = {key: value for key, value in derived.items() if getattr(lead, key) != value}
        if not changes and not extra:
            return None
        activities = list(extra)
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
        logger.fire("lead_import_started", business_id=str(business_id), records=len(envelope.leads))
        async with self.lock.hold(business_id):
            result = await self._import_records(settings, business_id, envelope)
        logger.fire(
            "lead_import_completed",
            level="warning" if result.failed else "info",
            business_id=str(business_id),
            created=result.created,
            updated=result.updated,
            skipped=result.skipped,
            failed=result.failed,
        )
        return result

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
                    logger.fire(
                        "lead_import_record_db_error", level="error", _exc_info=exc, business_id=str(business_id),
                        index=index,
                    )
                    raise
                logger.fire(
                    "lead_import_record_integrity_error", level="warning", business_id=str(business_id), index=index,
                    code=exc.code,
                )
                result.errors = [
                    RecordError(loc=[], msg="Record violates a database constraint", type="integrity_error")
                ]
            results.append(result)
        return ImportResult.from_results(results)

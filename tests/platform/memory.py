"""In-memory stand-ins for the Supabase repositories, for service tests that need no database."""

import uuid
from collections.abc import Collection, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from ai.schemas.enums import ActivityType
from app.channels.whatsapp import Button, WhatsAppSendError
from app.core.locks import LocalBusinessLock
from app.models import (
    Activity,
    AnalysisJob,
    AnalysisJobStatus,
    AnalysisTrigger,
    Business,
    IngestEvent,
    IngestStatus,
    Lead,
    ReplyDraft,
    ReplyDraftStatus,
    WhatsAppAccount,
)
from app.models.reply_draft import OPEN_DRAFT_STATUSES
from app.services.lead import LeadService
from app.services.replies import ApprovalTemplate, ReplyService

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


class FakeBusinesses:
    def __init__(self, business: Business) -> None:
        self.business = business

    async def get(self, business_id: uuid.UUID) -> Business | None:
        return self.business if business_id == self.business.id else None


class FakeJobs:
    """The analysis job queue (AnalysisJobRepository), with the same open-job and lease rules as db/004."""

    def __init__(self, clock: datetime = NOW) -> None:
        self.jobs: list[AnalysisJob] = []
        self.clock = clock

    def _replace(self, job: AnalysisJob, **changes: Any) -> AnalysisJob:
        updated = job.model_copy(update=changes | {"updated_at": self.clock})
        self.jobs[[j.id for j in self.jobs].index(job.id)] = updated
        return updated

    def open_for(self, lead_id: uuid.UUID) -> AnalysisJob | None:
        return next((j for j in self.jobs if j.lead_id == lead_id and j.open), None)

    async def enqueue(self, business_id: uuid.UUID, lead_id: uuid.UUID, trigger: AnalysisTrigger) -> AnalysisJob:
        if (job := self.open_for(lead_id)) is not None:
            return job
        job = AnalysisJob(
            id=uuid.uuid4(), business_id=business_id, lead_id=lead_id, trigger=trigger,
            status=AnalysisJobStatus.PENDING, attempts=0, max_attempts=5, run_after=self.clock, locked_until=None,
            worker=None, last_error=None, usage=None, cost_usd=None, created_at=self.clock, updated_at=self.clock,
            finished_at=None,
        )
        self.jobs.append(job)
        return job

    async def claim(self, worker: str, lease_seconds: int) -> AnalysisJob | None:
        due = [
            j for j in self.jobs
            if (j.status is AnalysisJobStatus.PENDING and j.run_after <= self.clock)
            or (j.status is AnalysisJobStatus.RUNNING and j.locked_until and j.locked_until < self.clock)
        ]
        if not due:
            return None
        job = min(due, key=lambda j: (j.run_after, j.created_at))
        return self._replace(
            job, status=AnalysisJobStatus.RUNNING, attempts=job.attempts + 1, worker=worker,
            locked_until=self.clock + timedelta(seconds=lease_seconds),
        )

    async def latest_for_lead(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> AnalysisJob | None:
        return next((j for j in reversed(self.jobs) if j.lead_id == lead_id), None)

    def _held(self, job: AnalysisJob) -> AnalysisJob | None:
        current = next(j for j in self.jobs if j.id == job.id)
        held = current.status is AnalysisJobStatus.RUNNING and current.worker == job.worker
        return current if held else None

    async def succeed(self, job: AnalysisJob, usage: dict[str, Any] | None, cost_usd: Decimal | None) -> bool:
        if (current := self._held(job)) is None:
            return False
        self._replace(
            current, status=AnalysisJobStatus.SUCCEEDED, usage=usage, cost_usd=cost_usd, last_error=None,
            finished_at=self.clock, locked_until=None,
        )
        return True

    async def retry(self, job: AnalysisJob, error: str, run_after: datetime) -> bool:
        if (current := self._held(job)) is None:
            return False
        self._replace(
            current, status=AnalysisJobStatus.PENDING, last_error=error, run_after=run_after, locked_until=None
        )
        return True

    async def fail(self, job: AnalysisJob, error: str) -> bool:
        if (current := self._held(job)) is None:
            return False
        self._replace(
            current, status=AnalysisJobStatus.FAILED, last_error=error, finished_at=self.clock, locked_until=None
        )
        return True


class FakeStore:
    """Leads and activities of one business, standing in for LeadRepository and ActivityRepository."""

    def __init__(self) -> None:
        self.leads: dict[uuid.UUID, Lead] = {}
        self.activities: list[Activity] = []
        self.clock = NOW
        self.jobs = FakeJobs()

    def _tick(self) -> datetime:
        self.clock += timedelta(seconds=1)
        return self.clock

    async def get(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
        return self.leads.get(lead_id)

    async def get_many(self, business_id: uuid.UUID, lead_ids: list[uuid.UUID]) -> list[Lead]:
        return [self.leads[lead_id] for lead_id in lead_ids if lead_id in self.leads]

    async def get_by_external_id(self, business_id: uuid.UUID, source: str, external_id: str) -> Lead | None:
        return next(
            (lead for lead in self.leads.values() if (lead.source, lead.external_id) == (source, external_id)), None
        )

    async def get_oldest_by_email(self, business_id: uuid.UUID, email: str) -> Lead | None:
        return next((lead for lead in self.leads.values() if lead.email == email), None)

    async def get_oldest_by_phone(self, business_id: uuid.UUID, phone: str) -> Lead | None:
        return next((lead for lead in self.leads.values() if lead.phone == phone), None)

    async def save(
        self,
        business_id: uuid.UUID,
        lead_id: uuid.UUID | None,
        values: dict[str, Any],
        activities: list[dict[str, Any]],
        analysis_trigger: AnalysisTrigger | None = None,
    ) -> Lead:
        if lead_id is None:
            row = {
                "id": uuid.uuid4(),
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
                "created_at": self.clock,
                "updated_at": self.clock,
            } | values
            lead = Lead.model_validate(row)
        else:
            lead = self.leads[lead_id].model_copy(update=values | {"updated_at": self._tick()})
        self.leads[lead.id] = lead
        for activity in activities:
            row = {"id": uuid.uuid4(), "business_id": business_id, "lead_id": lead.id, "channel": None} | activity
            self.activities.append(Activity.model_validate(row | {"created_at": self._tick()}))
        if analysis_trigger is not None:
            await self.jobs.enqueue(business_id, lead.id, analysis_trigger)
        return lead

    async def list_full(self, business_id: uuid.UUID) -> list[Lead]:
        return list(self.leads.values())

    async def all_for_lead(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> list[Activity]:
        return [activity for activity in self.activities if activity.lead_id == lead_id]

    async def latest_of_type(
        self, business_id: uuid.UUID, lead_id: uuid.UUID, activity_type: ActivityType
    ) -> Activity | None:
        return next(
            (a for a in reversed(self.activities) if a.lead_id == lead_id and a.activity_type is activity_type), None
        )

    async def all_for_business(self, business_id: uuid.UUID) -> list[Activity]:
        return list(self.activities)

    async def has_message(self, business_id: uuid.UUID, message_id: str) -> bool:
        return any(a.metadata.get("message_id") == message_id for a in self.activities)

    def types(self, lead_id: uuid.UUID) -> list[ActivityType]:
        return [activity.activity_type for activity in self.activities if activity.lead_id == lead_id]

    def add_activity(self, lead: Lead, activity_type: ActivityType) -> None:
        row = {"id": uuid.uuid4(), "business_id": lead.business_id, "lead_id": lead.id, "channel": None}
        fields = {"activity_type": activity_type, "description": "x", "metadata": {}, "created_at": self._tick()}
        self.activities.append(Activity.model_validate(row | fields))


def make_business(configuration: dict[str, Any], definitions: list[dict[str, Any]] | None = None) -> Business:
    return Business(
        id=uuid.uuid4(),
        name="Acme",
        slug="acme",
        industry=None,
        timezone="UTC",
        configuration=configuration,
        custom_field_definitions=definitions or [],
        ai_configuration={},
        created_at=NOW,
        updated_at=NOW,
    )


def make_service(business: Business, store: FakeStore) -> LeadService:
    service = LeadService(None, NOW)  # type: ignore[arg-type]  # repositories are replaced below
    service.businesses = FakeBusinesses(business)  # type: ignore[assignment]
    service.leads = store  # type: ignore[assignment]
    service.activities = store  # type: ignore[assignment]
    service.jobs = store.jobs  # type: ignore[assignment]
    service.lock = LocalBusinessLock()
    return service


class FakeDrafts:
    """ReplyDraftRepository, with the same one-undecided-draft-per-lead rule as ``uq_reply_drafts_open_lead``."""

    _UNDECIDED = OPEN_DRAFT_STATUSES | {ReplyDraftStatus.SENDING}

    def __init__(self) -> None:
        self.drafts: list[ReplyDraft] = []

    async def add(self, values: dict[str, Any]) -> ReplyDraft | None:
        if any(d.lead_id == values["lead_id"] and d.status in self._UNDECIDED for d in self.drafts):
            return None
        draft = ReplyDraft.model_validate(
            {
                "id": uuid.uuid4(), "status": ReplyDraftStatus.PENDING_APPROVAL, "edited": False, "decided_via": None,
                "approval_message_id": None, "sent_message_id": None, "last_error": None, "created_at": NOW,
                "updated_at": NOW, "decided_at": None, "sent_at": None,
            }
            | values
        )
        self.drafts.append(draft)
        return draft

    async def get(self, business_id: uuid.UUID, draft_id: uuid.UUID) -> ReplyDraft | None:
        return next((d for d in self.drafts if d.id == draft_id and d.business_id == business_id), None)

    async def with_status(
        self, business_id: uuid.UUID, statuses: Collection[ReplyDraftStatus], limit: int
    ) -> list[ReplyDraft]:
        matches = [d for d in reversed(self.drafts) if d.business_id == business_id and d.status in statuses]
        return matches[:limit]

    async def count(self, business_id: uuid.UUID, statuses: Collection[ReplyDraftStatus]) -> int:
        return len(await self.with_status(business_id, statuses, len(self.drafts)))

    async def for_lead(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> list[ReplyDraft]:
        return [d for d in reversed(self.drafts) if d.business_id == business_id and d.lead_id == lead_id]

    async def awaiting_edit(self, business_id: uuid.UUID) -> ReplyDraft | None:
        drafts = await self.with_status(business_id, [ReplyDraftStatus.AWAITING_EDIT], 1)
        return drafts[0] if drafts else None

    async def transition(
        self, draft: ReplyDraft, from_statuses: Collection[ReplyDraftStatus], values: dict[str, Any]
    ) -> ReplyDraft | None:
        current = await self.get(draft.business_id, draft.id)
        if current is None or current.status not in from_statuses:
            return None
        updated = current.model_copy(update=values)
        self.drafts[self.drafts.index(current)] = updated
        return updated

    def only(self) -> ReplyDraft:
        assert len(self.drafts) == 1, self.drafts
        return self.drafts[0]


class FakeAccounts:
    def __init__(self, *accounts: WhatsAppAccount) -> None:
        self.accounts = {account.business_id: account for account in accounts}

    async def get(self, business_id: uuid.UUID) -> WhatsAppAccount | None:
        return self.accounts.get(business_id)

    async def get_by_phone_number_id(self, phone_number_id: str) -> WhatsAppAccount | None:
        return next((a for a in self.accounts.values() if a.phone_number_id == phone_number_id), None)

    async def save(self, business_id: uuid.UUID, values: dict[str, Any]) -> WhatsAppAccount:
        account = WhatsAppAccount.model_validate(
            {"business_id": business_id, "created_at": NOW, "updated_at": NOW, "display_phone": None} | values
        )
        self.accounts[business_id] = account
        return account

    async def delete(self, business_id: uuid.UUID) -> None:
        self.accounts.pop(business_id, None)


class FakeEvents:
    """IngestEventRepository with the claim_ingest_event rules (stale processing events are not modelled)."""

    def __init__(self) -> None:
        self.events: dict[tuple[uuid.UUID, str, str], IngestEvent] = {}

    async def claim(
        self,
        business_id: uuid.UUID,
        source: str,
        external_event_id: str,
        event_type: str,
        payload: dict[str, Any],
        stale_seconds: int = 300,
    ) -> IngestEvent | None:
        key = (business_id, source, external_event_id)
        if (event := self.events.get(key)) is not None:
            if event.status is not IngestStatus.FAILED:
                return None
            event = event.model_copy(update={"status": IngestStatus.PROCESSING, "attempts": event.attempts + 1})
        else:
            event = IngestEvent(
                id=uuid.uuid4(), business_id=business_id, source=source, external_event_id=external_event_id,
                event_type=event_type, status=IngestStatus.PROCESSING, attempts=1, payload=payload, last_error=None,
                created_at=NOW, updated_at=NOW, processed_at=None,
            )
        self.events[key] = event
        return event

    async def finish(self, event: IngestEvent, status: IngestStatus, error: str | None = None) -> None:
        key = (event.business_id, event.source, event.external_event_id)
        self.events[key] = self.events[key].model_copy(update={"status": status, "last_error": error})

    def statuses(self) -> list[IngestStatus]:
        return [event.status for event in self.events.values()]


class FakeSender:
    """Records what would be sent. ``fail[method]`` raises that error on the next call of ``method``."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, Any]] = []  # (method, to, text, extra)
        self.fail: dict[str, WhatsAppSendError] = {}

    def _record(self, method: str, to: str, text: str, extra: Any = None) -> str:
        if (error := self.fail.pop(method, None)) is not None:
            raise error
        self.sent.append((method, to, text, extra))
        return f"wamid.{len(self.sent)}"

    async def send_text(self, phone_number_id: str, to: str, body: str) -> str:
        return self._record("text", to, body)

    async def send_buttons(self, phone_number_id: str, to: str, body: str, buttons: Sequence[Button]) -> str:
        return self._record("buttons", to, body, [b.id for b in buttons])

    async def send_template(
        self,
        phone_number_id: str,
        to: str,
        name: str,
        language: str,
        body_params: Sequence[str],
        button_payloads: Sequence[str] = (),
    ) -> str:
        return self._record("template", to, name, (list(body_params), list(button_payloads)))

    def to(self, phone: str) -> list[str]:
        return [text for _, to, text, _ in self.sent if to == phone]


OWNER_PHONE = "+972501111111"
PHONE_NUMBER_ID = "1098765432"


def make_account(business: Business) -> WhatsAppAccount:
    return WhatsAppAccount(
        business_id=business.id, phone_number_id=PHONE_NUMBER_ID, display_phone="+972500000000",
        owner_phone=OWNER_PHONE, created_at=NOW, updated_at=NOW,
    )


def make_replies(
    service: LeadService,
    accounts: FakeAccounts,
    sender: FakeSender | None = None,
    template: ApprovalTemplate | None = None,
) -> ReplyService:
    replies = ReplyService(None, service, sender or FakeSender(), template, NOW)  # type: ignore[arg-type]
    replies.drafts = FakeDrafts()  # type: ignore[assignment]
    replies.accounts = accounts  # type: ignore[assignment]
    return replies

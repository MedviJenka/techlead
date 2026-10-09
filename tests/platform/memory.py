"""In-memory stand-ins for the Supabase repositories, for service tests that need no database."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from ai.schemas.enums import ActivityType
from app.core.locks import LocalBusinessLock
from app.models import Activity, AnalysisJob, AnalysisJobStatus, AnalysisTrigger, Business, Lead
from app.services.lead import LeadService

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

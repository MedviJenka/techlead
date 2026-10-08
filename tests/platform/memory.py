"""In-memory stand-ins for the Supabase repositories, for service tests that need no database."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ai.schemas.enums import ActivityType
from app.models import Activity, Business, Lead
from app.services.lead import LeadService

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


class FakeBusinesses:
    def __init__(self, business: Business) -> None:
        self.business = business

    async def get(self, business_id: uuid.UUID) -> Business | None:
        return self.business if business_id == self.business.id else None


class FakeStore:
    """Leads and activities of one business, standing in for LeadRepository and ActivityRepository."""

    def __init__(self) -> None:
        self.leads: dict[uuid.UUID, Lead] = {}
        self.activities: list[Activity] = []
        self.clock = NOW

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
        return lead

    async def list_full(self, business_id: uuid.UUID) -> list[Lead]:
        return list(self.leads.values())

    async def all_for_lead(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> list[Activity]:
        return [activity for activity in self.activities if activity.lead_id == lead_id]

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
    return service

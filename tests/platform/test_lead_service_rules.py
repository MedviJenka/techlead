"""LeadService scoring, priority and custom-field rules over in-memory repositories (no database needed).

The Supabase-backed tests (test_leads_api.py) cover persistence; these cover the decisions the service makes.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ai.schemas.enums import ActivityType, Priority
from app.models import Activity, Business, Lead
from app.schemas import LeadCreate, LeadUpdate
from app.schemas.configuration import BusinessConfiguration, CustomFieldDefinition
from app.schemas.lead_import import ImportEnvelope, ImportOutcome
from app.services.lead import InvalidCustomFields, LeadService
from tests.platform.factories import raw_lead

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
# Base 40; "Customer responded" +10 and "Budget known" +10 are the rules these tests trigger.
RULES: list[dict[str, Any]] = [
    {
        "id": "budget_known",
        "label": "Budget known",
        "points": 10,
        "when": [{"fact": "budget_known", "op": "eq", "value": True}],
    },
    {"id": "responded", "label": "Responded", "points": 10, "when": [{"fact": "replied", "op": "eq", "value": True}]},
]


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


def _business(configuration: dict[str, Any], definitions: list[dict[str, Any]] | None = None) -> Business:
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


def _service(business: Business, store: FakeStore) -> LeadService:
    service = LeadService(None, NOW)  # type: ignore[arg-type]  # repositories are replaced below
    service.businesses = FakeBusinesses(business)  # type: ignore[assignment]
    service.leads = store  # type: ignore[assignment]
    service.activities = store  # type: ignore[assignment]
    return service


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def business() -> Business:
    return _business({"scoring": {"base_score": 40, "rules": RULES}})


@pytest.fixture
def service(business: Business, store: FakeStore) -> LeadService:
    return _service(business, store)


async def test_create_scores_and_prioritizes(service: LeadService, business: Business, store: FakeStore) -> None:
    lead = await service.create(business.id, LeadCreate(source="web", custom_fields={"budget": 1000}))

    assert (lead.lead_score, lead.priority) == (50, Priority.MEDIUM)
    assert store.types(lead.id) == [ActivityType.LEAD_CREATED, ActivityType.SCORE_CHANGED]
    score_event = store.activities[-1]
    assert score_event.metadata == {"from": None, "to": 50, "deterministic": 50, "ai": None, "rules": ["budget_known"]}


async def test_explicit_priority_wins_until_the_score_changes(
    service: LeadService, business: Business, store: FakeStore
) -> None:
    lead = await service.create(business.id, LeadCreate(source="web", priority=Priority.CRITICAL))
    assert (lead.lead_score, lead.priority) == (40, Priority.CRITICAL)

    lead = await service.update(business.id, lead.id, LeadUpdate(notes="called, no answer"))
    assert (lead.lead_score, lead.priority) == (40, Priority.CRITICAL)

    lead = await service.update(business.id, lead.id, LeadUpdate(custom_fields={"budget": 900}))
    assert (lead.lead_score, lead.priority) == (50, Priority.MEDIUM)


async def test_update_records_status_and_score_changes(
    service: LeadService, business: Business, store: FakeStore
) -> None:
    lead = await service.create(business.id, LeadCreate(source="web"))

    await service.update(business.id, lead.id, LeadUpdate(status="won", custom_fields={"budget": 10}))

    assert store.types(lead.id)[2:] == [
        ActivityType.LEAD_UPDATED,
        ActivityType.STATUS_CHANGED,
        ActivityType.SCORE_CHANGED,
    ]


async def test_unchanged_update_writes_nothing(service: LeadService, business: Business, store: FakeStore) -> None:
    lead = await service.create(business.id, LeadCreate(source="web", notes="hi"))
    count = len(store.activities)

    same = await service.update(business.id, lead.id, LeadUpdate(notes="hi"))

    assert same == lead and len(store.activities) == count


async def test_rescore_applies_new_activity_and_settings(business: Business, store: FakeStore) -> None:
    service = _service(business, store)
    lead = await service.create(business.id, LeadCreate(source="web"))
    store.add_activity(lead, ActivityType.EMAIL_RECEIVED)

    result = await service.rescore(business.id)
    assert (result.total, result.changed) == (1, 1)
    assert store.leads[lead.id].lead_score == 50
    assert (await _service(business, store).rescore(business.id)).changed == 0

    stricter = _business(
        {"scoring": {"base_score": 0, "rules": RULES}, "priority": {"critical": 9, "high": 8, "medium": 7}}
    )
    stricter.id = business.id
    assert (await _service(stricter, store).rescore(business.id)).changed == 1
    assert (store.leads[lead.id].lead_score, store.leads[lead.id].priority) == (10, Priority.CRITICAL)


async def test_score_breakdown_is_live(service: LeadService, business: Business, store: FakeStore) -> None:
    lead = await service.create(business.id, LeadCreate(source="web"))
    store.add_activity(lead, ActivityType.WHATSAPP_RECEIVED)

    breakdown = await service.score(business.id, lead.id)

    assert (breakdown.final, [rule.id for rule in breakdown.matched]) == (50, ["responded"])
    assert store.leads[lead.id].lead_score == 40  # stored score changes only on the next write or rescore


async def test_read_adds_the_next_follow_up(service: LeadService, business: Business) -> None:
    lead = await service.create(business.id, LeadCreate(source="web", priority=Priority.HIGH))

    read = await service.read(lead)

    assert read.follow_up is not None
    assert (read.follow_up.reason, read.follow_up.due_at) == ("first_response", NOW + timedelta(hours=4))


async def test_custom_fields_are_checked_against_definitions(store: FakeStore) -> None:
    business = _business({}, [CustomFieldDefinition(key="rooms", label="Rooms", type="number").model_dump()])
    service = _service(business, store)

    with pytest.raises(InvalidCustomFields) as error:
        await service.create(business.id, LeadCreate(source="web", custom_fields={"rooms": "four"}))
    assert error.value.details == [
        {"loc": ["custom_fields", "rooms"], "msg": "must be a number", "type": "custom_field"}
    ]
    lead = await service.create(business.id, LeadCreate(source="web", custom_fields={"rooms": 4}))
    with pytest.raises(InvalidCustomFields):
        await service.update(business.id, lead.id, LeadUpdate(custom_fields={"rooms": True}))


async def test_import_blends_upstream_ai_score_and_reports_custom_field_errors(store: FakeStore) -> None:
    definitions = [CustomFieldDefinition(key="city", label="City", type="select", options=["Haifa"]).model_dump()]
    business = _business({}, definitions)
    service = _service(business, store)
    good = raw_lead(4, custom_fields={"city": "Haifa"})  # lead_005: proposal sent, replied, 30-day timeframe
    bad = raw_lead(0)  # lead_001: city "Tel Aviv" is not an option

    result = await service.import_batch(business.id, ImportEnvelope(leads=[good, bad]))

    assert [record.outcome for record in result.results] == [ImportOutcome.CREATED, ImportOutcome.FAILED]
    assert result.results[1].errors[0].loc == ["custom_fields", "city"]
    lead = store.leads[result.results[0].lead_id]  # type: ignore[index]
    # Deterministic 100 (40 + 10 + 20 + 10 + 20), upstream AI 89: 100 * 0.6 + 89 * 0.4 = 95.6.
    # The source's own priority ("high") is explicit input, so it is kept.
    assert (lead.lead_score, lead.priority) == (96, Priority.HIGH)


async def test_business_with_default_configuration(store: FakeStore) -> None:
    business = _business({})
    lead = await _service(business, store).create(business.id, LeadCreate(source="web"))
    assert lead.lead_score == BusinessConfiguration().scoring.base_score

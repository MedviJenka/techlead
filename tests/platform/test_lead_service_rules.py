"""LeadService scoring, priority and custom-field rules over in-memory repositories (no database needed).

The Supabase-backed tests (test_leads_api.py) cover persistence; these cover the decisions the service makes.
"""

from datetime import timedelta
from typing import Any

import pytest

from ai.schemas.enums import ActivityType, Priority
from app.models import Business
from app.schemas import LeadCreate, LeadUpdate
from app.schemas.configuration import BusinessConfiguration, CustomFieldDefinition
from app.schemas.lead_import import ImportEnvelope, ImportOutcome
from app.services.lead import InvalidCustomFields, LeadService
from tests.platform.factories import raw_lead
from tests.platform.memory import NOW, FakeStore, make_business, make_service

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


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def business() -> Business:
    return make_business({"scoring": {"base_score": 40, "rules": RULES}})


@pytest.fixture
def service(business: Business, store: FakeStore) -> LeadService:
    return make_service(business, store)


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
    service = make_service(business, store)
    lead = await service.create(business.id, LeadCreate(source="web"))
    store.add_activity(lead, ActivityType.EMAIL_RECEIVED)

    result = await service.rescore(business.id)
    assert (result.total, result.changed) == (1, 1)
    assert store.leads[lead.id].lead_score == 50
    assert (await make_service(business, store).rescore(business.id)).changed == 0

    stricter = make_business(
        {"scoring": {"base_score": 0, "rules": RULES}, "priority": {"critical": 9, "high": 8, "medium": 7}}
    )
    stricter.id = business.id
    assert (await make_service(stricter, store).rescore(business.id)).changed == 1
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
    business = make_business({}, [CustomFieldDefinition(key="rooms", label="Rooms", type="number").model_dump()])
    service = make_service(business, store)

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
    business = make_business({}, definitions)
    service = make_service(business, store)
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
    business = make_business({})
    lead = await make_service(business, store).create(business.id, LeadCreate(source="web"))
    assert lead.lead_score == BusinessConfiguration().scoring.base_score

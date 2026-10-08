"""Data-access layer against the test Supabase project: tenant scoping, dedup lookups and paging."""

from datetime import UTC, datetime, timedelta

from supabase import AsyncClient

from ai.schemas.enums import ActivityType, Priority
from app.models import Business, Lead
from app.repositories import ActivityRepository, LeadRepository
from app.schemas import LeadListParams
from tests.platform.factories import make_activity, make_business, make_lead

T0 = datetime(2026, 10, 7, 8, 0, tzinfo=UTC)


def _at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


async def _lead(db: AsyncClient, business: Business, minutes: int, **fields: object) -> Lead:
    return await make_lead(db, business, created_at=_at(minutes), **fields)


# --- LeadRepository ---


async def test_get_is_tenant_scoped(db: AsyncClient) -> None:
    acme, other = await make_business(db, "acme"), await make_business(db, "other")
    lead = await make_lead(db, acme)
    repo = LeadRepository(db)

    assert await repo.get(acme.id, lead.id) == lead
    assert await repo.get(other.id, lead.id) is None


async def test_dedup_lookups(db: AsyncClient) -> None:
    acme, other = await make_business(db, "acme"), await make_business(db, "other")
    newer = await _lead(db, acme, 10, email="a@x.com", phone="+1234567")
    older = await _lead(db, acme, 5, email="a@x.com", phone="+1234567", external_id="e-1")
    await _lead(db, other, 0, email="a@x.com", external_id="e-1")
    repo = LeadRepository(db)

    assert await repo.get_by_external_id(acme.id, "website", "e-1") == older
    assert await repo.get_by_external_id(acme.id, "email", "e-1") is None
    assert await repo.get_oldest_by_email(acme.id, "a@x.com") == older
    assert await repo.get_oldest_by_phone(acme.id, "+1234567") == older
    assert newer != older


async def test_list_page_orders_filters_and_counts(db: AsyncClient) -> None:
    acme, other = await make_business(db, "acme"), await make_business(db, "other")
    first = await _lead(db, acme, 0, status="new", priority=Priority.HIGH, last_name="Cohen")
    second = await _lead(db, acme, 1, status="qualified", priority=Priority.HIGH, source="whatsapp")
    third = await _lead(db, acme, 1, status="new", company_name="100%_Real")
    await _lead(db, other, 2, status="new")
    repo = LeadRepository(db)

    async def ids(**params: object) -> tuple[list[object], int]:
        leads, total = await repo.list_page(acme.id, LeadListParams.model_validate(params))
        return [lead.id for lead in leads], total

    tie = sorted([second.id, third.id], reverse=True)
    assert await ids() == ([*tie, first.id], 3)
    assert await ids(limit=1, offset=1) == ([tie[1]], 3)
    assert await ids(status="new") == ([third.id, first.id], 2)
    assert await ids(priority="high", status="qualified") == ([second.id], 1)
    assert await ids(source="WhatsApp") == ([second.id], 1)
    assert await ids(q="COHEN") == ([first.id], 1)
    assert await ids(q="0%_r") == ([third.id], 1)
    assert await ids(q="0%x") == ([], 0)
    assert await ids(q='a,b"(c)') == ([], 0)  # filter syntax characters are matched literally, not parsed


async def test_save_inserts_and_updates_with_activities(db: AsyncClient) -> None:
    acme = await make_business(db, "acme")
    repo = LeadRepository(db)
    created_event = {"activity_type": ActivityType.LEAD_CREATED, "description": "Lead created", "metadata": {}}

    lead = await repo.save(acme.id, None, {"source": "web", "email": "a@x.com"}, [created_event])
    updated = await repo.save(
        acme.id, lead.id, {"status": "qualified"}, [{"activity_type": ActivityType.STATUS_CHANGED, "description": "x"}]
    )

    assert (lead.status, lead.custom_fields, lead.raw_payload) == ("new", {}, {})
    assert (updated.id, updated.status, updated.email, updated.created_at) == (
        lead.id,
        "qualified",
        "a@x.com",
        lead.created_at,
    )
    assert updated.updated_at > lead.updated_at
    activities, total = await ActivityRepository(db).list_for_lead(acme.id, lead.id, limit=10, offset=0)
    assert total == 2
    assert {a.activity_type for a in activities} == {ActivityType.LEAD_CREATED, ActivityType.STATUS_CHANGED}


async def test_list_all_returns_every_lead_of_the_business(db: AsyncClient) -> None:
    acme, other = await make_business(db, "acme"), await make_business(db, "other")
    mine = {(await make_lead(db, acme)).id for _ in range(3)}
    await make_lead(db, other)

    assert {lead.id for lead in await LeadRepository(db).list_all(acme.id)} == mine


async def test_list_page_never_returns_raw_payload(db: AsyncClient) -> None:
    acme = await make_business(db, "acme")
    await make_lead(db, acme, raw_payload={"secret": 1})

    [lead], _ = await LeadRepository(db).list_page(acme.id, LeadListParams())

    assert "raw_payload" not in lead.model_dump()


# --- ActivityRepository ---


async def test_activities_are_chronological_and_scoped(db: AsyncClient) -> None:
    acme = await make_business(db, "acme")
    lead, other_lead = await make_lead(db, acme), await make_lead(db, acme)
    late = await make_activity(db, lead, created_at=_at(5))
    early = await make_activity(db, lead, created_at=_at(1))
    await make_activity(db, other_lead, created_at=_at(0))
    repo = ActivityRepository(db)

    activities, total = await repo.list_for_lead(acme.id, lead.id, limit=10, offset=0)
    assert [a.id for a in activities] == [early.id, late.id]
    assert total == 2
    page, _ = await repo.list_for_lead(acme.id, lead.id, limit=1, offset=1)
    assert [a.id for a in page] == [late.id]


async def test_recent_activities_are_newest_first_and_scoped(db: AsyncClient) -> None:
    acme, other = await make_business(db, "acme"), await make_business(db, "other")
    lead = await make_lead(db, acme)
    early = await make_activity(db, lead, created_at=_at(1))
    late = await make_activity(db, lead, created_at=_at(5))
    await make_activity(db, await make_lead(db, other), created_at=_at(9))
    repo = ActivityRepository(db)

    assert [a.id for a in await repo.recent(acme.id, limit=10)] == [late.id, early.id]
    assert [a.id for a in await repo.recent(acme.id, limit=1)] == [late.id]

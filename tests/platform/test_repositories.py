"""Data-access layer against real PostgreSQL: tenant scoping, dedup lookups, paging and dashboard aggregates."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from ai.schemas.enums import ActivityType, Channel, Priority
from app.models import Business, Lead
from app.repositories import ActivityRepository, DashboardRepository, DashboardRules, LeadRepository
from app.schemas import LeadListParams
from tests.platform.factories import make_activity, make_business, make_lead

T0 = datetime(2026, 10, 7, 8, 0, tzinfo=UTC)

RULES = DashboardRules(
    hot_priorities=frozenset({Priority.HIGH, Priority.CRITICAL}),
    closed_statuses=frozenset({"won", "lost"}),
    new_status="new",
    qualified_status="qualified",
    proposal_status="proposal_sent",
    inactive_status="unresponsive",
    stale_before=T0 - timedelta(hours=12),
    priority_rank={Priority.CRITICAL: 4, Priority.HIGH: 3, Priority.MEDIUM: 2, Priority.LOW: 1},
)


def _at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


async def _lead(session: AsyncSession, business: Business, minutes: int, **fields: object) -> Lead:
    return await make_lead(session, business, created_at=_at(minutes), **fields)


# --- LeadRepository ---


async def test_get_is_tenant_scoped(session: AsyncSession) -> None:
    acme, other = await make_business(session, "acme"), await make_business(session, "other")
    lead = await make_lead(session, acme)
    repo = LeadRepository(session)

    assert await repo.get(acme.id, lead.id) is lead
    assert await repo.get(other.id, lead.id) is None


async def test_dedup_lookups(session: AsyncSession) -> None:
    acme, other = await make_business(session, "acme"), await make_business(session, "other")
    newer = await _lead(session, acme, 10, email="a@x.com", phone="+1234567")
    older = await _lead(session, acme, 5, email="a@x.com", phone="+1234567", external_id="e-1")
    await _lead(session, other, 0, email="a@x.com", external_id="e-1")
    repo = LeadRepository(session)

    assert await repo.get_by_external_id(acme.id, "website", "e-1") is older
    assert await repo.get_by_external_id(acme.id, "email", "e-1") is None
    assert await repo.get_oldest_by_email(acme.id, "a@x.com") is older
    assert await repo.get_oldest_by_phone(acme.id, "+1234567") is older
    assert newer is not older


async def test_list_page_orders_filters_and_counts(session: AsyncSession) -> None:
    acme, other = await make_business(session, "acme"), await make_business(session, "other")
    first = await _lead(session, acme, 0, status="new", priority=Priority.HIGH, last_name="Cohen")
    second = await _lead(session, acme, 1, status="qualified", priority=Priority.HIGH, source="whatsapp")
    third = await _lead(session, acme, 1, status="new", company_name="100%_Real")
    await _lead(session, other, 2, status="new")
    repo = LeadRepository(session)

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


async def test_list_page_never_loads_raw_payload(session: AsyncSession) -> None:
    acme = await make_business(session, "acme")
    await make_lead(session, acme, raw_payload={"secret": 1})
    session.expunge_all()

    [lead], _ = await LeadRepository(session).list_page(acme.id, LeadListParams())

    with pytest.raises(InvalidRequestError):
        _ = lead.raw_payload


# --- ActivityRepository ---


async def test_activities_are_chronological_and_scoped(session: AsyncSession) -> None:
    acme = await make_business(session, "acme")
    lead, other_lead = await make_lead(session, acme), await make_lead(session, acme)
    late = await make_activity(session, lead, created_at=_at(5))
    early = await make_activity(session, lead, created_at=_at(1))
    await make_activity(session, other_lead, created_at=_at(0))
    repo = ActivityRepository(session)

    activities, total = await repo.list_for_lead(acme.id, lead.id, limit=10, offset=0)
    assert [a.id for a in activities] == [early.id, late.id]
    assert total == 2
    page, _ = await repo.list_for_lead(acme.id, lead.id, limit=1, offset=1)
    assert [a.id for a in page] == [late.id]


# --- DashboardRepository ---


async def test_dashboard_aggregates(session: AsyncSession) -> None:
    acme, other = await make_business(session, "acme"), await make_business(session, "other")
    stale = T0 - timedelta(days=1)
    await _lead(session, acme, 0, status="new", priority=Priority.HIGH, lead_score=90)
    await _lead(session, acme, 1, status="qualified", priority=Priority.CRITICAL, lead_score=40, last_contact_at=_at(5))
    await _lead(session, acme, 2, status="won", priority=Priority.CRITICAL, lead_score=99, last_contact_at=stale)
    await _lead(session, acme, 3, status="unresponsive", source="email", lead_score=10, last_contact_at=_at(5))
    await _lead(session, acme, 4, status="proposal_sent", priority=Priority.LOW, last_contact_at=_at(5))
    await _lead(session, other, 0, status="new", priority=Priority.HIGH, lead_score=1)
    repo = DashboardRepository(session)

    counts = await repo.counts(acme.id, RULES)

    assert (counts.total, counts.new, counts.hot, counts.qualified, counts.waiting_for_proposal) == (5, 1, 3, 1, 1)
    # new lead (never contacted) is the only open lead needing follow-up; inactive adds the unresponsive one.
    assert (counts.needs_follow_up, counts.inactive) == (1, 1)
    assert counts.average_score == Decimal("59.75")
    assert await repo.distribution(acme.id, "source") == [("website", 4), ("email", 1)]
    assert await repo.distribution(acme.id, "status") == [
        ("new", 1),
        ("proposal_sent", 1),
        ("qualified", 1),
        ("unresponsive", 1),
        ("won", 1),
    ]
    assert await repo.score_distribution(acme.id) == {"0-39": 1, "40-69": 1, "70-100": 2, "unknown": 1}
    top = await repo.top_leads(acme.id, RULES)
    assert [(lead.status, lead.lead_score) for lead in top] == [
        ("qualified", 40),
        ("new", 90),
        ("proposal_sent", None),
        ("unresponsive", 10),
    ]


async def test_dashboard_for_empty_business(session: AsyncSession) -> None:
    acme = await make_business(session, "acme")
    repo = DashboardRepository(session)

    counts = await repo.counts(acme.id, RULES)

    assert (counts.total, counts.needs_follow_up, counts.average_score) == (0, 0, None)
    assert await repo.distribution(acme.id, "status") == []
    assert await repo.score_distribution(acme.id) == {"0-39": 0, "40-69": 0, "70-100": 0, "unknown": 0}
    assert await repo.recent_activities(acme.id) == []
    assert await repo.top_leads(acme.id, RULES) == []


async def test_recent_activities_newest_first_with_lead_name(session: AsyncSession) -> None:
    acme, other = await make_business(session, "acme"), await make_business(session, "other")
    named = await make_lead(session, acme, first_name="Omer", last_name="Tal")
    anonymous = await make_lead(session, acme)
    await make_activity(session, named, created_at=_at(1))
    latest = await make_activity(
        session, anonymous, created_at=_at(2), activity_type=ActivityType.PHONE_CALL, channel=Channel.PHONE
    )
    await make_activity(session, await make_lead(session, other), created_at=_at(3))
    repo = DashboardRepository(session)

    rows = await repo.recent_activities(acme.id)

    assert [row.lead_name for row in rows] == [None, "Omer Tal"]
    assert rows[0].id == latest.id
    assert rows[0].channel is Channel.PHONE
    assert len(await repo.recent_activities(acme.id, limit=1)) == 1

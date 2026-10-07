"""Database-level guarantees: defaults, JSONB, constraints and tenant integrity."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai.schemas import ActivityType, Channel, Priority
from app.models import Activity, Business, Lead


async def _business(session: AsyncSession, slug: str) -> Business:
    business = Business(name=slug.title(), slug=slug)
    session.add(business)
    await session.flush()
    return business


async def _lead(session: AsyncSession, business: Business, **fields: object) -> Lead:
    lead = Lead(business_id=business.id, source="website", **fields)
    session.add(lead)
    await session.flush()
    return lead


async def test_lead_defaults_and_jsonb_roundtrip(session: AsyncSession) -> None:
    business = await _business(session, "acme")
    lead = await _lead(session, business, priority=Priority.HIGH, custom_fields={"rooms": 4, "location": "Tel Aviv"})
    await session.commit()
    session.expunge_all()

    loaded = await session.get_one(Lead, lead.id)
    assert loaded.status == "new"
    assert loaded.priority is Priority.HIGH
    assert loaded.custom_fields == {"rooms": 4, "location": "Tel Aviv"}
    assert loaded.raw_payload == {}
    assert loaded.created_at.tzinfo is not None


async def test_lead_score_must_be_0_to_100(session: AsyncSession) -> None:
    business = await _business(session, "acme")

    with pytest.raises(IntegrityError, match="ck_leads_lead_score_range"):
        await _lead(session, business, lead_score=101)


async def test_enum_columns_reject_unknown_values(session: AsyncSession) -> None:
    business = await _business(session, "acme")

    with pytest.raises(IntegrityError, match="ck_leads_lead_priority"):
        await session.execute(
            text("INSERT INTO leads (business_id, source, priority) VALUES (:b, 'web', 'urgent')"),
            {"b": business.id},
        )


async def test_external_id_is_unique_per_business_and_source(session: AsyncSession) -> None:
    acme, other = await _business(session, "acme"), await _business(session, "other")
    await _lead(session, acme, external_id="ext-1")
    await _lead(session, other, external_id="ext-1")  # another tenant may reuse the id
    await _lead(session, acme, external_id=None)
    await _lead(session, acme, external_id=None)  # many leads without an external id are fine

    with pytest.raises(IntegrityError, match="uq_leads_business_id_source_external_id"):
        await _lead(session, acme, external_id="ext-1")


async def test_activity_cannot_reference_another_tenants_lead(session: AsyncSession) -> None:
    acme, other = await _business(session, "acme"), await _business(session, "other")
    foreign_lead = await _lead(session, other)

    session.add(
        Activity(
            business_id=acme.id,
            lead_id=foreign_lead.id,
            activity_type=ActivityType.LEAD_CREATED,
            description="cross-tenant",
        )
    )
    with pytest.raises(IntegrityError, match="fk_activities_business_id_lead_id_leads"):
        await session.flush()


async def test_tables_have_row_level_security_enabled(session: AsyncSession) -> None:
    rows = await session.execute(
        text("SELECT relname, relrowsecurity FROM pg_class WHERE relname IN ('businesses', 'leads', 'activities')")
    )

    assert dict(rows.tuples().all()) == {"businesses": True, "leads": True, "activities": True}


async def test_deleting_business_cascades_to_leads_and_activities(session: AsyncSession) -> None:
    business = await _business(session, "acme")
    lead = await _lead(session, business)
    session.add(
        Activity(
            business_id=business.id,
            lead_id=lead.id,
            activity_type=ActivityType.WHATSAPP_RECEIVED,
            channel=Channel.WHATSAPP,
            description="Hi, is it still available?",
            metadata_={"message_id": "wamid.1"},
        )
    )
    await session.commit()

    await session.delete(business)
    await session.commit()

    assert await session.scalar(select(func.count()).select_from(Lead)) == 0
    assert await session.scalar(select(func.count()).select_from(Activity)) == 0

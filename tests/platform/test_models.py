"""Database-level guarantees of `db/*.sql` on the test Supabase project: defaults, JSONB, constraints, tenancy."""

import pytest
from postgrest.exceptions import APIError
from supabase import AsyncClient

from ai.schemas import ActivityType, Channel, Priority
from tests.platform.factories import make_activity, make_business, make_lead


async def test_lead_defaults_and_jsonb_roundtrip(db: AsyncClient) -> None:
    business = await make_business(db, "acme")
    custom_fields = {"rooms": 4, "location": "Tel Aviv"}

    lead = await make_lead(db, business, priority=Priority.HIGH, custom_fields=custom_fields)

    assert lead.status == "new"
    assert lead.priority is Priority.HIGH
    assert lead.custom_fields == {"rooms": 4, "location": "Tel Aviv"}
    assert lead.raw_payload == {}
    assert lead.created_at.tzinfo is not None


async def test_lead_score_must_be_0_to_100(db: AsyncClient) -> None:
    business = await make_business(db, "acme")

    with pytest.raises(APIError, match="ck_leads_lead_score_range"):
        await make_lead(db, business, lead_score=101)


async def test_enum_columns_reject_unknown_values(db: AsyncClient) -> None:
    business = await make_business(db, "acme")

    with pytest.raises(APIError, match="ck_leads_lead_priority"):
        await make_lead(db, business, priority="urgent")


async def test_external_id_is_unique_per_business_and_source(db: AsyncClient) -> None:
    acme, other = await make_business(db, "acme"), await make_business(db, "other")
    await make_lead(db, acme, external_id="ext-1")
    await make_lead(db, other, external_id="ext-1")  # another tenant may reuse the id
    await make_lead(db, acme, external_id=None)
    await make_lead(db, acme, external_id=None)  # many leads without an external id are fine

    with pytest.raises(APIError, match="uq_leads_business_id_source_external_id"):
        await make_lead(db, acme, external_id="ext-1")


async def test_activity_cannot_reference_another_tenants_lead(db: AsyncClient) -> None:
    acme, other = await make_business(db, "acme"), await make_business(db, "other")
    foreign_lead = await make_lead(db, other)

    with pytest.raises(APIError, match="fk_activities_business_id_lead_id_leads"):
        await make_activity(db, foreign_lead, business_id=acme.id, description="cross-tenant")


async def test_deleting_business_cascades_to_leads_and_activities(db: AsyncClient) -> None:
    business = await make_business(db, "acme")
    lead = await make_lead(db, business)
    await make_activity(
        db,
        lead,
        activity_type=ActivityType.WHATSAPP_RECEIVED,
        channel=Channel.WHATSAPP,
        description="Hi, is it still available?",
        metadata={"message_id": "wamid.1"},
    )

    await db.table("businesses").delete().eq("id", str(business.id)).execute()

    assert (await db.table("leads").select("id").eq("business_id", str(business.id)).execute()).data == []
    assert (await db.table("activities").select("id").eq("business_id", str(business.id)).execute()).data == []

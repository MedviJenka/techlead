"""Phase 7 tables and functions on the test Supabase project: ingest idempotency, reply drafts, WhatsApp numbers."""

import pytest
from postgrest.exceptions import APIError
from supabase import AsyncClient

from ai.schemas.enums import ActivityType
from app.models import IngestStatus, ReplyDraftStatus
from app.models.reply_draft import OPEN_DRAFT_STATUSES
from app.repositories import ActivityRepository, IngestEventRepository, ReplyDraftRepository, WhatsAppAccountRepository
from tests.platform.factories import make_activity, make_business, make_lead


async def test_an_event_is_claimed_once_and_again_only_after_it_failed(db: AsyncClient) -> None:
    business = await make_business(db)
    events = IngestEventRepository(db)

    first = await events.claim(business.id, "whatsapp", "wamid.A", "text", {"a": 1})
    assert first is not None and (first.status, first.attempts) == (IngestStatus.PROCESSING, 1)
    assert await events.claim(business.id, "whatsapp", "wamid.A", "text", {"a": 1}) is None  # in progress

    await events.finish(first, IngestStatus.FAILED, "boom")
    retried = await events.claim(business.id, "whatsapp", "wamid.A", "text", {"a": 1})
    assert retried is not None and (retried.attempts, retried.last_error) == (2, None)

    await events.finish(retried, IngestStatus.PROCESSED)
    assert await events.claim(business.id, "whatsapp", "wamid.A", "text", {"a": 1}) is None


async def test_a_stuck_event_is_taken_over_after_the_stale_period(db: AsyncClient) -> None:
    business = await make_business(db)
    events = IngestEventRepository(db)
    assert await events.claim(business.id, "whatsapp", "wamid.S", "text", {}) is not None
    taken = await events.claim(business.id, "whatsapp", "wamid.S", "text", {}, stale_seconds=0)
    assert taken is not None and taken.attempts == 2


async def test_one_undecided_draft_per_lead_and_conditional_decisions(db: AsyncClient) -> None:
    business = await make_business(db)
    lead = await make_lead(db, business)
    drafts = ReplyDraftRepository(db)
    values = {"business_id": business.id, "lead_id": lead.id, "channel": "whatsapp", "message": "Hi!"}

    draft = await drafts.add(values)
    assert draft is not None and draft.status is ReplyDraftStatus.PENDING_APPROVAL
    assert await drafts.add(values) is None
    assert await drafts.count(business.id, OPEN_DRAFT_STATUSES) == 1

    rejected = await drafts.transition(draft, OPEN_DRAFT_STATUSES, {"status": ReplyDraftStatus.REJECTED})
    assert rejected is not None and rejected.status is ReplyDraftStatus.REJECTED
    assert await drafts.transition(draft, OPEN_DRAFT_STATUSES, {"status": ReplyDraftStatus.SENDING}) is None
    assert await drafts.add(values) is not None  # the lead may get a new draft once the last one is decided


async def test_a_whatsapp_number_belongs_to_one_business(db: AsyncClient) -> None:
    acme, other = await make_business(db), await make_business(db, slug="other")
    accounts = WhatsAppAccountRepository(db)
    values = {"phone_number_id": "1098765432", "owner_phone": "+972501111111", "display_phone": None}

    await accounts.save(acme.id, values)
    saved = await accounts.save(acme.id, values | {"owner_phone": "+972502222222"})
    assert saved.owner_phone == "+972502222222"
    assert (await accounts.get_by_phone_number_id("1098765432")) == saved

    with pytest.raises(APIError) as raised:
        await accounts.save(other.id, values)
    assert raised.value.code == "23505"


async def test_messages_are_found_by_id_and_first_responses_by_lead(db: AsyncClient) -> None:
    business = await make_business(db)
    lead = await make_lead(db, business)
    sent = await make_activity(db, lead, activity_type="whatsapp_sent", metadata={"message_id": "wamid.X"})
    await make_activity(db, lead, activity_type="phone_call")
    activities = ActivityRepository(db)

    assert await activities.has_message(business.id, "wamid.X")
    assert not await activities.has_message(business.id, "wamid.Y")
    firsts = await activities.first_of_types(business.id, [ActivityType.WHATSAPP_SENT, ActivityType.PHONE_CALL])
    assert firsts == {lead.id: sent.created_at}

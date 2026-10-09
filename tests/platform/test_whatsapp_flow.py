"""Phase 7 end to end on in-memory repositories: a WhatsApp message becomes a lead, NewLeadFlow drafts a first reply,
the owner approves, edits or rejects it on their phone (or the dashboard), and the reply reaches the lead.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from ai.schemas import Channel, FollowupDraft, NextActionRecommendation
from ai.schemas.enums import ActivityType
from app.analysis.drafting import CrewReplyDrafter
from app.analysis.first_reply import FirstReply
from app.analysis.flow import NewLeadFlow
from app.channels.whatsapp import WhatsAppSendError, parse_messages
from app.core.errors import BadGatewayError, ConflictError
from app.models import Business, DecisionChannel, IngestStatus, Lead, ReplyDraftStatus
from app.services.inbox import InboxError, WhatsAppInbox
from app.services.lead import InboundChannelMessage, LeadService
from app.services.replies import ApprovalTemplate, ReplyService, approval_text, parse_decision
from tests.fakes import ScriptedLLM
from tests.platform.memory import (
    NOW,
    OWNER_PHONE,
    FakeAccounts,
    FakeDrafts,
    FakeEvents,
    FakeSender,
    FakeStore,
    make_account,
    make_business,
    make_replies,
    make_service,
)
from tests.platform.test_analysis import FakeEngine
from tests.platform.test_whatsapp_channel import button_reply, delivery, text

LEAD_PHONE = "+972521234567"


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def business() -> Business:
    return make_business({"scoring": {"base_score": 40, "rules": []}, "phone_region": "IL"})


@pytest.fixture
def service(business: Business, store: FakeStore) -> LeadService:
    return make_service(business, store)


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture
def replies(service: LeadService, business: Business, sender: FakeSender) -> ReplyService:
    return make_replies(service, FakeAccounts(make_account(business)), sender)


@pytest.fixture
def drafts(replies: ReplyService) -> FakeDrafts:
    return replies.drafts  # type: ignore[return-value]


def inbound(body: str | None = "Hi, looking for a 4-room flat", message_id: str = "wamid.A", **fields: Any) -> Any:
    values = {
        "channel": Channel.WHATSAPP, "message_id": message_id, "phone": LEAD_PHONE, "sender_name": "Dana Levi",
        "body": body, "kind": "text", "sent_at": NOW,
    }
    return InboundChannelMessage(**(values | fields))


async def new_lead(service: LeadService, business: Business) -> Lead:
    received = await service.receive_message(business.id, inbound())
    assert received is not None
    return received[0]


async def drafted(replies: ReplyService, business: Business, lead: Lead, message: str = "Hi Dana! Which area?") -> Any:
    draft = await replies.create_draft(business.id, lead.id, Channel.WHATSAPP, message, "Qualify")
    assert draft is not None
    return draft


# --- receiving ---


async def test_first_message_creates_a_whatsapp_lead_queued_for_analysis(
    service: LeadService, business: Business, store: FakeStore
) -> None:
    received = await service.receive_message(business.id, inbound())

    assert received is not None
    lead, created = received
    assert created
    assert (lead.source, lead.phone, lead.first_name, lead.last_name) == ("whatsapp", LEAD_PHONE, "Dana", "Levi")
    assert (lead.notes, lead.last_contact_at) == ("Hi, looking for a 4-room flat", NOW)
    assert store.types(lead.id) == [
        ActivityType.LEAD_CREATED, ActivityType.WHATSAPP_RECEIVED, ActivityType.SCORE_CHANGED
    ]
    message = store.activities[1]
    assert (message.channel, message.metadata["message_id"], message.metadata["body"]) == (
        Channel.WHATSAPP, "wamid.A", "Hi, looking for a 4-room flat",
    )
    assert store.jobs.open_for(lead.id) is not None


async def test_later_messages_join_the_lead_with_the_same_phone(
    service: LeadService, business: Business, store: FakeStore
) -> None:
    lead = await new_lead(service, business)
    # A national number is read in the business's country (IL), so it is the same phone.
    received = await service.receive_message(business.id, inbound("Still there?", "wamid.B", phone="052-123-4567"))

    assert received is not None
    assert (received[0].id, received[1]) == (lead.id, False)
    assert len(store.leads) == 1
    assert store.types(lead.id).count(ActivityType.WHATSAPP_RECEIVED) == 2
    assert ActivityType.LEAD_UPDATED not in store.types(lead.id)  # the message itself explains the new contact time
    assert len(store.jobs.jobs) == 1


async def test_a_message_already_recorded_is_ignored(
    service: LeadService, business: Business, store: FakeStore
) -> None:
    await new_lead(service, business)
    assert await service.receive_message(business.id, inbound()) is None
    assert len(store.activities) == 3


async def test_media_without_text_is_described_by_its_kind(service: LeadService, business: Business) -> None:
    lead, _ = await service.receive_message(business.id, inbound(None, kind="image")) or (None, None)
    assert lead is not None and lead.notes is None


# --- approval request ---


async def test_draft_goes_to_the_owner_with_approve_edit_reject(
    service: LeadService, replies: ReplyService, business: Business, sender: FakeSender, drafts: FakeDrafts
) -> None:
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)

    assert await replies.request_approval(make_account(business), draft, lead, "Hi, looking for a 4-room flat")

    [(method, to, body, buttons)] = sender.sent
    assert (method, to) == ("buttons", OWNER_PHONE)
    assert "Dana Levi" in body and '"Hi, looking for a 4-room flat"' in body and body.endswith("Hi Dana! Which area?")
    assert buttons == [f"approve:{draft.id}", f"edit:{draft.id}", f"reject:{draft.id}"]
    assert drafts.only().approval_message_id == "wamid.1"


async def test_a_long_inbound_message_is_shortened_but_the_draft_never_is(
    service: LeadService, replies: ReplyService, business: Business
) -> None:
    lead = await new_lead(service, business)
    reply = "x" * 700
    body = approval_text(lead, await drafted(replies, business, lead, reply), "y" * 2000)
    assert len(body) <= 1024 and body.endswith(reply) and "…" in body


async def test_owner_outside_the_window_gets_the_template(
    service: LeadService, business: Business, sender: FakeSender
) -> None:
    template = ApprovalTemplate("approve_reply", "en")
    replies = make_replies(service, FakeAccounts(make_account(business)), sender, template)
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)
    sender.fail["buttons"] = WhatsAppSendError("Re-engagement message", 131047)

    assert await replies.request_approval(make_account(business), draft, lead, None)

    [(method, _, name, (params, payloads))] = sender.sent
    assert (method, name, params) == ("template", "approve_reply", ["Dana Levi", "Hi Dana! Which area?"])
    assert payloads == [f"approve:{draft.id}", f"edit:{draft.id}", f"reject:{draft.id}"]


async def test_undelivered_approval_request_waits_on_the_dashboard(
    service: LeadService, replies: ReplyService, business: Business, sender: FakeSender, drafts: FakeDrafts
) -> None:
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)
    sender.fail["buttons"] = WhatsAppSendError("Re-engagement message", 131047)

    assert not await replies.request_approval(make_account(business), draft, lead, None)

    saved = drafts.only()
    assert saved.status is ReplyDraftStatus.PENDING_APPROVAL
    assert saved.last_error and "Re-engagement message" in saved.last_error
    assert [(d.id, name) for d, name in await replies.pending(business.id, 10)] == [(draft.id, "Dana Levi")]


# --- decisions ---


async def test_approval_sends_the_reply_and_records_it_on_the_lead(
    service: LeadService, replies: ReplyService, business: Business, sender: FakeSender, store: FakeStore
) -> None:
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)

    sent = await replies.approve(business.id, draft.id, DecisionChannel.DASHBOARD)

    assert (sent.status, sent.sent_message_id, sent.decided_via, sent.edited) == (
        ReplyDraftStatus.SENT, "wamid.1", DecisionChannel.DASHBOARD, False,
    )
    assert sender.to(LEAD_PHONE) == ["Hi Dana! Which area?"]
    recorded = next(a for a in store.activities if a.activity_type is ActivityType.WHATSAPP_SENT)
    assert (recorded.channel, recorded.metadata["draft_id"], recorded.metadata["message_id"]) == (
        Channel.WHATSAPP, str(draft.id), "wamid.1",
    )
    assert store.leads[lead.id].last_contact_at == NOW
    with pytest.raises(ConflictError, match="already sent"):
        await replies.approve(business.id, draft.id, DecisionChannel.WHATSAPP)
    assert len(sender.to(LEAD_PHONE)) == 1


async def test_dashboard_edit_sends_the_new_text(
    service: LeadService, replies: ReplyService, business: Business, sender: FakeSender
) -> None:
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)

    sent = await replies.approve(business.id, draft.id, DecisionChannel.DASHBOARD, "Hi Dana, which area suits you?")

    assert (sent.message, sent.edited) == ("Hi Dana, which area suits you?", True)
    assert sender.to(LEAD_PHONE) == ["Hi Dana, which area suits you?"]


async def test_failed_send_can_be_approved_again(
    service: LeadService, replies: ReplyService, business: Business, sender: FakeSender, drafts: FakeDrafts
) -> None:
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)
    sender.fail["text"] = WhatsAppSendError("Re-engagement message", 131047)

    with pytest.raises(BadGatewayError, match="24-hour"):
        await replies.approve(business.id, draft.id, DecisionChannel.DASHBOARD)
    assert drafts.only().status is ReplyDraftStatus.FAILED

    assert (await replies.approve(business.id, draft.id, DecisionChannel.DASHBOARD)).status is ReplyDraftStatus.SENT


async def test_rejected_draft_is_never_sent(
    service: LeadService, replies: ReplyService, business: Business, sender: FakeSender
) -> None:
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)

    assert (await replies.reject(business.id, draft.id, DecisionChannel.DASHBOARD)).status is ReplyDraftStatus.REJECTED
    with pytest.raises(ConflictError, match="already rejected"):
        await replies.approve(business.id, draft.id, DecisionChannel.DASHBOARD)
    assert sender.sent == []


async def test_without_a_whatsapp_number_nothing_can_be_sent(
    service: LeadService, business: Business, sender: FakeSender
) -> None:
    replies = make_replies(service, FakeAccounts(), sender)
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)
    with pytest.raises(ConflictError, match="not connected"):
        await replies.approve(business.id, draft.id, DecisionChannel.DASHBOARD)


def test_decision_ids_round_trip() -> None:
    draft_id = uuid.uuid4()
    assert parse_decision(f"approve:{draft_id}") == ("approve", draft_id)
    assert parse_decision("approve:not-a-uuid") is None
    assert parse_decision(f"delete:{draft_id}") is None


# --- the owner on WhatsApp ---


def owner(message: dict[str, Any]) -> Any:
    [parsed] = parse_messages(delivery(message))
    return parsed


async def test_owner_approves_with_a_tap(
    service: LeadService, replies: ReplyService, business: Business, sender: FakeSender, drafts: FakeDrafts
) -> None:
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)

    await replies.handle_owner_message(make_account(business), owner(button_reply(f"approve:{draft.id}")))

    assert sender.to(LEAD_PHONE) == ["Hi Dana! Which area?"]
    assert sender.to(OWNER_PHONE) == ["Sent to Dana Levi."]
    assert drafts.only().decided_via is DecisionChannel.WHATSAPP


async def test_owner_edits_then_types_the_reply(
    service: LeadService, replies: ReplyService, business: Business, sender: FakeSender, drafts: FakeDrafts
) -> None:
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)
    account = make_account(business)

    await replies.handle_owner_message(account, owner(button_reply(f"edit:{draft.id}")))
    assert drafts.only().status is ReplyDraftStatus.AWAITING_EDIT
    await replies.handle_owner_message(account, owner(text("Hi Dana, call you at 5?", "wamid.O", "972501111111")))

    assert sender.to(LEAD_PHONE) == ["Hi Dana, call you at 5?"]
    assert sender.to(OWNER_PHONE)[-1] == "Sent your version to Dana Levi."
    assert (drafts.only().status, drafts.only().edited) == (ReplyDraftStatus.SENT, True)


async def test_owner_rejects_and_a_late_approve_is_refused(
    service: LeadService, replies: ReplyService, business: Business, sender: FakeSender
) -> None:
    lead = await new_lead(service, business)
    draft = await drafted(replies, business, lead)
    account = make_account(business)

    await replies.handle_owner_message(account, owner(button_reply(f"reject:{draft.id}")))
    await replies.handle_owner_message(account, owner(button_reply(f"approve:{draft.id}", "wamid.C")))

    assert sender.to(LEAD_PHONE) == []
    assert sender.to(OWNER_PHONE) == ["Rejected. Nothing was sent to Dana Levi.", "This reply was already rejected"]


async def test_owner_cannot_decide_on_another_business_draft(
    replies: ReplyService, business: Business, sender: FakeSender
) -> None:
    await replies.handle_owner_message(make_account(business), owner(button_reply(f"approve:{uuid.uuid4()}")))
    assert sender.to(OWNER_PHONE)[0].startswith("Reply draft") and sender.to(LEAD_PHONE) == []


async def test_owner_chatting_with_nothing_pending_is_told_so(
    replies: ReplyService, business: Business, sender: FakeSender
) -> None:
    await replies.handle_owner_message(make_account(business), owner(text("hello?", sender="972501111111")))
    assert sender.to(OWNER_PHONE) == ["Nothing is waiting for your approval right now."]


# --- the inbox (webhook deliveries) ---


@pytest.fixture
def inbox(service: LeadService, replies: ReplyService) -> WhatsAppInbox:
    inbox = WhatsAppInbox(None, service, replies)  # type: ignore[arg-type]
    inbox.events = FakeEvents()  # type: ignore[assignment]
    inbox.accounts = replies.accounts
    return inbox


async def test_a_redelivered_message_is_processed_once(inbox: WhatsAppInbox, store: FakeStore) -> None:
    payload = delivery(text("Hi"))
    first = await inbox.handle(payload)
    again = await inbox.handle(payload)

    assert (first.processed, again.processed, again.duplicates) == (1, 0, 1)
    assert len(store.leads) == 1 and len(store.activities) == 3
    assert inbox.events.statuses() == [IngestStatus.PROCESSED]  # type: ignore[attr-defined]


async def test_owner_messages_are_decisions_not_leads(
    inbox: WhatsAppInbox, store: FakeStore, sender: FakeSender
) -> None:
    await inbox.handle(delivery(text("hello?", sender="972501111111")))
    assert store.leads == {}
    assert sender.to(OWNER_PHONE) == ["Nothing is waiting for your approval right now."]


async def test_unknown_numbers_and_reactions_are_ignored(inbox: WhatsAppInbox, store: FakeStore) -> None:
    reaction = {"from": "972521234567", "id": "wamid.R", "timestamp": "1", "type": "reaction", "reaction": {}}
    unknown = await inbox.handle(delivery(text("Hi"), phone_number_id="999"))
    ignored = await inbox.handle(delivery(reaction))
    assert (unknown.ignored, ignored.ignored) == (1, 1)
    assert store.leads == {}


async def test_a_failed_message_is_retried_on_redelivery(
    inbox: WhatsAppInbox, service: LeadService, store: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = delivery(text("Hi"))
    real = service.receive_message

    async def down(*args: Any) -> Any:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(service, "receive_message", down)
    with pytest.raises(InboxError):
        await inbox.handle(payload)
    assert inbox.events.statuses() == [IngestStatus.FAILED]  # type: ignore[attr-defined]

    monkeypatch.setattr(service, "receive_message", real)
    assert (await inbox.handle(payload)).processed == 1
    assert len(store.leads) == 1


# --- first reply (NewLeadFlow's last step) ---


class FakeDrafter:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[NextActionRecommendation | None] = []

    async def draft(self, business: Any, lead: Any, activities: Any, recommendation: Any) -> FollowupDraft:
        self.calls.append(recommendation)
        if self.error:
            raise self.error
        return FollowupDraft(
            channel=Channel.WHATSAPP, message="Hi Dana! Which area are you looking in?", objective="Qualify area",
            tone="warm",
        )


def first_reply(service: LeadService, replies: ReplyService, drafter: FakeDrafter) -> FirstReply:
    return FirstReply(service, replies, drafter, lambda: datetime(2026, 10, 9, 12, 0, 30, tzinfo=UTC))


async def test_new_whatsapp_lead_gets_a_drafted_reply_for_approval(
    service: LeadService, replies: ReplyService, business: Business, sender: FakeSender, drafts: FakeDrafts
) -> None:
    lead = await new_lead(service, business)
    drafter = FakeDrafter()
    flow = NewLeadFlow(service, FakeEngine(), "openai/test", None, first_reply(service, replies, drafter))

    await flow.run(business.id, lead.id)

    draft = drafts.only()
    assert draft.message == "Hi Dana! Which area are you looking in?"
    assert draft.status is ReplyDraftStatus.PENDING_APPROVAL
    assert drafter.calls[0] is not None and drafter.calls[0].action.value == "call"
    assert sender.sent[0][0:2] == ("buttons", OWNER_PHONE)


async def test_no_draft_without_whatsapp_or_once_answered(
    service: LeadService, business: Business, sender: FakeSender, store: FakeStore
) -> None:
    lead = await new_lead(service, business)
    drafter = FakeDrafter()
    not_connected = make_replies(service, FakeAccounts(), sender)
    assert await first_reply(service, not_connected, drafter).run(business.id, lead.id, None) is None

    replies = make_replies(service, FakeAccounts(make_account(business)), sender)
    store.add_activity(lead, ActivityType.PHONE_CALL)
    assert await first_reply(service, replies, drafter).run(business.id, lead.id, None) is None
    assert drafter.calls == []


async def test_a_retried_job_does_not_draft_twice(
    service: LeadService, replies: ReplyService, business: Business, drafts: FakeDrafts
) -> None:
    lead = await new_lead(service, business)
    step = first_reply(service, replies, FakeDrafter())
    assert await step.run(business.id, lead.id, None) is not None
    assert await step.run(business.id, lead.id, None) is None
    assert len(drafts.drafts) == 1


async def test_a_failed_draft_does_not_fail_the_analysis(
    service: LeadService, replies: ReplyService, business: Business, store: FakeStore
) -> None:
    lead = await new_lead(service, business)
    step = first_reply(service, replies, FakeDrafter(RuntimeError("LLM down")))
    outcome = await NewLeadFlow(service, FakeEngine(), "openai/test", None, step).run(business.id, lead.id)
    assert outcome.lead.ai_summary is not None
    assert ActivityType.AI_ANALYSIS in store.types(lead.id)


async def test_real_conversation_crew_drafts_the_first_reply(
    service: LeadService, replies: ReplyService, business: Business, drafts: FakeDrafts, sender: FakeSender
) -> None:
    lead = await new_lead(service, business)
    reply = FollowupDraft(
        channel=Channel.WHATSAPP, message="Hi Dana! Happy to help. Which area are you looking in?",
        objective="Learn the area", tone="warm",
    )
    llm = ScriptedLLM({"generate_followup_task": [reply]})
    step = first_reply(service, replies, CrewReplyDrafter(lambda tier: llm))

    draft = await step.run(business.id, lead.id, None)

    assert llm.calls == ["generate_followup_task"]
    assert draft is not None and draft.message == reply.message
    assert drafts.only().objective == "Learn the area"
    assert sender.sent[0][2].endswith(reply.message)

"""AI-drafted replies and the owner's decision on them (MAIN_PLAN §42, §66).

The owner decides where they already are: the draft goes to their WhatsApp with Approve / Edit / Reject buttons.
Edit asks for the reply as they want it; their next message is sent instead. The dashboard is the fallback and uses
the same ``approve`` / ``reject``. Every decision is a conditional state change, so only the first one counts.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from postgrest.exceptions import APIError
from supabase import AsyncClient

from ai.schemas.enums import Channel
from app.channels.whatsapp import Button, WhatsAppCloudClient, WhatsAppMessage, WhatsAppSender, WhatsAppSendError
from app.channels.whatsapp.client import INTERACTIVE_BODY_MAX_LENGTH
from app.core.errors import BadGatewayError, ConflictError, DomainError, NotFoundError, UnprocessableError
from app.core.logger import Logger
from app.models import DecisionChannel, Lead, ReplyDraft, ReplyDraftStatus, WhatsAppAccount
from app.models.reply_draft import OPEN_DRAFT_STATUSES, SENDABLE_DRAFT_STATUSES
from app.repositories import ReplyDraftRepository, WhatsAppAccountRepository
from app.schemas.reply import WhatsAppConnection
from app.services.lead import LeadService, OutboundChannelMessage
from settings import Settings

logger = Logger(__name__)

UNIQUE_VIOLATION = "23505"
APPROVE, EDIT, REJECT = "approve", "edit", "reject"
_INBOUND_PREVIEW_MIN = 40


def decision_id(action: str, draft_id: uuid.UUID) -> str:
    """The id of an approval button (``approve:<draft id>``); it comes back in the webhook when tapped."""
    return f"{action}:{draft_id}"


def parse_decision(reply_id: str) -> tuple[str, uuid.UUID] | None:
    action, _, draft_id = reply_id.partition(":")
    if action not in (APPROVE, EDIT, REJECT):
        return None
    try:
        return action, uuid.UUID(draft_id)
    except ValueError:
        return None


def lead_label(lead: Lead) -> str:
    return " ".join(filter(None, (lead.first_name, lead.last_name))) or lead.phone or "the lead"


def approval_text(lead: Lead, draft: ReplyDraft, inbound: str | None) -> str:
    """The approval request: who wrote, what they wrote (shortened to fit) and the full suggested reply."""
    header = f"New WhatsApp lead: {lead_label(lead)}"
    if lead.lead_score is not None:
        header += f"\nScore {lead.lead_score}" + (f" ({lead.priority.value})" if lead.priority else "")
    suggestion = f"\n\nSuggested reply:\n{draft.message}"
    room = INTERACTIVE_BODY_MAX_LENGTH - len(header) - len(suggestion) - len('\n\nThey wrote: ""')
    if inbound and room >= _INBOUND_PREVIEW_MIN:
        quote = inbound if len(inbound) <= room else inbound[: room - 1] + "…"
        header += f'\n\nThey wrote: "{quote}"'
    return header + suggestion


@dataclass(frozen=True)
class ApprovalTemplate:
    """An approved template for owners outside the 24-hour window: body ``{{1}}`` lead, ``{{2}}`` suggested reply,
    and three quick-reply buttons (Approve, Edit, Reject) in that order.
    """

    name: str
    language: str

    @classmethod
    def from_settings(cls, config: Settings) -> "ApprovalTemplate | None":
        if not config.WHATSAPP_APPROVAL_TEMPLATE:
            return None
        return cls(config.WHATSAPP_APPROVAL_TEMPLATE, config.WHATSAPP_APPROVAL_TEMPLATE_LANGUAGE)


def whatsapp_sender(config: Settings) -> WhatsAppCloudClient:
    return WhatsAppCloudClient(
        config.WHATSAPP_ACCESS_TOKEN, config.WHATSAPP_GRAPH_VERSION, graph_url=config.WHATSAPP_GRAPH_URL
    )


class ReplyService:
    def __init__(
        self,
        db: AsyncClient,
        leads: LeadService,
        sender: WhatsAppSender,
        template: ApprovalTemplate | None,
        now: datetime,
    ) -> None:
        self.drafts = ReplyDraftRepository(db)
        self.accounts = WhatsAppAccountRepository(db)
        self.leads = leads
        self.sender = sender
        self.template = template
        self.now = now

    # --- the WhatsApp connection ---

    async def account(self, business_id: uuid.UUID) -> WhatsAppAccount | None:
        await self.leads.settings(business_id)
        return await self.accounts.get(business_id)

    async def connect(self, business_id: uuid.UUID, data: WhatsAppConnection) -> WhatsAppAccount:
        await self.leads.settings(business_id)
        try:
            account = await self.accounts.save(business_id, data.model_dump())
        except APIError as exc:
            if exc.code != UNIQUE_VIOLATION:
                raise
            raise ConflictError("This WhatsApp number is connected to another business") from exc
        logger.fire("whatsapp_connected", business_id=str(business_id), phone_number_id=data.phone_number_id)
        return account

    async def disconnect(self, business_id: uuid.UUID) -> None:
        await self.leads.settings(business_id)
        await self.accounts.delete(business_id)
        logger.fire("whatsapp_disconnected", business_id=str(business_id))

    # --- drafts ---

    async def pending(self, business_id: uuid.UUID, limit: int) -> list[tuple[ReplyDraft, str]]:
        """Drafts waiting for a decision (or whose sending failed), newest first, with their lead's name."""
        await self.leads.settings(business_id)
        statuses = [*OPEN_DRAFT_STATUSES, ReplyDraftStatus.FAILED]
        drafts = await self.drafts.with_status(business_id, statuses, limit)
        leads = await self.leads.leads.get_many(business_id, list({draft.lead_id for draft in drafts}))
        labels = {lead.id: lead_label(lead) for lead in leads}
        return [(draft, labels.get(draft.lead_id, "the lead")) for draft in drafts]

    async def for_lead(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> list[ReplyDraft]:
        await self.leads.get(business_id, lead_id)
        return await self.drafts.for_lead(business_id, lead_id)

    async def create_draft(
        self, business_id: uuid.UUID, lead_id: uuid.UUID, channel: Channel, message: str, objective: str | None
    ) -> ReplyDraft | None:
        """None when the lead already has an undecided draft."""
        values = {
            "business_id": business_id,
            "lead_id": lead_id,
            "channel": channel,
            "message": message,
            "objective": objective,
        }
        return await self.drafts.add(values)

    async def request_approval(
        self, account: WhatsAppAccount, draft: ReplyDraft, lead: Lead, inbound: str | None
    ) -> bool:
        """Send the draft to the owner's WhatsApp with Approve / Edit / Reject. False when it could not be sent: the
        draft then waits on the dashboard, with the reason in ``last_error``.
        """
        buttons = [
            Button(decision_id(APPROVE, draft.id), "Approve"),
            Button(decision_id(EDIT, draft.id), "Edit"),
            Button(decision_id(REJECT, draft.id), "Reject"),
        ]
        to = account.owner_phone
        message_id, error = None, None
        try:
            try:
                text = approval_text(lead, draft, inbound)
                message_id = await self.sender.send_buttons(account.phone_number_id, to, text, buttons)
            except WhatsAppSendError as exc:
                if not (exc.outside_window and self.template):
                    raise
                # The owner has not written to the business number in 24 hours: only a template reaches them.
                message_id = await self.sender.send_template(
                    account.phone_number_id, to, self.template.name, self.template.language,
                    [lead_label(lead), draft.message], [b.id for b in buttons],
                )
        except WhatsAppSendError as exc:
            error = f"Approval request not delivered to the owner's WhatsApp: {exc}"
        values = {"approval_message_id": message_id, "last_error": error}
        await self.drafts.transition(draft, OPEN_DRAFT_STATUSES, values)
        logger.fire(
            "reply_approval_requested" if error is None else "reply_approval_request_failed",
            level="info" if error is None else "warning",
            business_id=str(draft.business_id),
            lead_id=str(draft.lead_id),
            draft_id=str(draft.id),
            error=error,
        )
        return error is None

    async def _require(self, business_id: uuid.UUID, draft_id: uuid.UUID) -> ReplyDraft:
        draft = await self.drafts.get(business_id, draft_id)
        if draft is None:
            raise NotFoundError(f"Reply draft {draft_id} not found")
        return draft

    async def _decided(self, business_id: uuid.UUID, draft_id: uuid.UUID) -> ConflictError:
        current = await self._require(business_id, draft_id)
        return ConflictError(f"This reply was already {current.status.value.replace('_', ' ')}")

    async def approve(
        self, business_id: uuid.UUID, draft_id: uuid.UUID, via: DecisionChannel, message: str | None = None
    ) -> ReplyDraft:
        """Send the draft (or ``message``, the owner's edit) to the lead and record it on the lead's timeline."""
        draft = await self._require(business_id, draft_id)
        account = await self.accounts.get(business_id)
        if account is None:
            raise ConflictError("WhatsApp is not connected for this business")
        lead = await self.leads.get(business_id, draft.lead_id)
        if lead.phone is None:
            raise UnprocessableError("The lead has no phone number")
        text = (message or draft.message).strip()
        edited = draft.edited or text != draft.message
        claim = {
            "status": ReplyDraftStatus.SENDING,
            "message": text,
            "edited": edited,
            "decided_via": via,
            "decided_at": self.now,
            "last_error": None,
        }
        claimed = await self.drafts.transition(draft, SENDABLE_DRAFT_STATUSES, claim)
        if claimed is None:
            raise await self._decided(business_id, draft_id)
        log: dict[str, Any] = {
            "business_id": str(business_id), "lead_id": str(lead.id), "draft_id": str(draft.id), "via": via.value
        }
        try:
            message_id = await self.sender.send_text(account.phone_number_id, lead.phone, text)
        except WhatsAppSendError as exc:
            reason = (
                "The lead's 24-hour WhatsApp window has closed; reply from your phone instead"
                if exc.outside_window
                else str(exc)
            )
            await self.drafts.transition(
                claimed, {ReplyDraftStatus.SENDING}, {"status": ReplyDraftStatus.FAILED, "last_error": reason}
            )
            logger.fire("reply_send_failed", level="warning", error=reason, **log)
            raise BadGatewayError(f"The reply was not sent: {reason}") from exc
        outbound = OutboundChannelMessage(
            Channel.WHATSAPP, message_id, text, {"draft_id": str(draft.id), "edited": edited, "approved_via": via.value}
        )
        await self.leads.record_outbound(business_id, lead.id, outbound)
        sent = await self.drafts.transition(
            claimed,
            {ReplyDraftStatus.SENDING},
            {"status": ReplyDraftStatus.SENT, "sent_message_id": message_id, "sent_at": self.now},
        )
        seconds = round((self.now - lead.created_at).total_seconds())
        logger.fire("reply_sent", edited=edited, seconds_since_lead=seconds, **log)
        return sent or claimed

    async def reject(self, business_id: uuid.UUID, draft_id: uuid.UUID, via: DecisionChannel) -> ReplyDraft:
        draft = await self._require(business_id, draft_id)
        values = {"status": ReplyDraftStatus.REJECTED, "decided_via": via, "decided_at": self.now}
        rejected = await self.drafts.transition(draft, SENDABLE_DRAFT_STATUSES, values)
        if rejected is None:
            raise await self._decided(business_id, draft_id)
        logger.fire("reply_rejected", business_id=str(business_id), draft_id=str(draft_id), via=via.value)
        return rejected

    async def start_edit(self, business_id: uuid.UUID, draft_id: uuid.UUID) -> ReplyDraft:
        """The owner tapped Edit: their next WhatsApp message to the business number is sent instead."""
        draft = await self._require(business_id, draft_id)
        values = {"status": ReplyDraftStatus.AWAITING_EDIT}
        editing = await self.drafts.transition(draft, {ReplyDraftStatus.PENDING_APPROVAL}, values)
        if editing is None:
            raise await self._decided(business_id, draft_id)
        return editing

    # --- the owner's WhatsApp ---

    async def handle_owner_message(self, account: WhatsAppAccount, message: WhatsAppMessage) -> None:
        """A message from the owner: a tapped decision button, or the text of a reply they are editing."""
        business_id = account.business_id
        decision = parse_decision(message.reply_id) if message.reply_id else None
        try:
            if decision is not None:
                answer = await self._decide(business_id, *decision)
            elif message.text and (draft := await self.drafts.awaiting_edit(business_id)):
                await self.approve(business_id, draft.id, DecisionChannel.WHATSAPP, message.text)
                answer = f"Sent your version to {await self._name(business_id, draft)}."
            else:
                answer = "Nothing is waiting for your approval right now."
        except DomainError as exc:
            answer = exc.message
        try:
            await self.sender.send_text(account.phone_number_id, account.owner_phone, answer)
        except WhatsAppSendError as exc:
            logger.fire("owner_answer_failed", level="warning", business_id=str(business_id), error=str(exc))

    async def _decide(self, business_id: uuid.UUID, action: str, draft_id: uuid.UUID) -> str:
        if action == APPROVE:
            draft = await self.approve(business_id, draft_id, DecisionChannel.WHATSAPP)
            return f"Sent to {await self._name(business_id, draft)}."
        if action == EDIT:
            draft = await self.start_edit(business_id, draft_id)
            return f"Send me the reply as you want it, and I'll send it to {await self._name(business_id, draft)}."
        draft = await self.reject(business_id, draft_id, DecisionChannel.WHATSAPP)
        return f"Rejected. Nothing was sent to {await self._name(business_id, draft)}."

    async def _name(self, business_id: uuid.UUID, draft: ReplyDraft) -> str:
        return lead_label(await self.leads.get(business_id, draft.lead_id))

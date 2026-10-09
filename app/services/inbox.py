"""Inbound WhatsApp messages (MAIN_PLAN §66): webhook delivery -> ingest event -> lead or owner decision.

Each message is claimed in ``ingest_events`` before it is processed, so a redelivered webhook changes nothing. A
message that fails is left ``failed`` and the delivery is answered with an error: Meta redelivers it, and only the
failed messages are processed again.
"""

from dataclasses import dataclass

from supabase import AsyncClient

from ai.schemas.enums import Channel
from app.channels.whatsapp import WhatsAppMessage, parse_messages
from app.core.errors import DomainError
from app.core.logger import Logger
from app.models import IngestStatus, WhatsAppAccount
from app.repositories import IngestEventRepository, WhatsAppAccountRepository
from app.services.lead import InboundChannelMessage, LeadService
from app.services.replies import ReplyService

logger = Logger(__name__)

SOURCE = "whatsapp"
# Message types that carry nothing for the lead's history.
IGNORED_KINDS = frozenset({"reaction", "system", "unsupported", "ephemeral", "request_welcome"})
_MAX_ERROR_LENGTH = 2000


class InboxError(DomainError):
    """Some messages of a delivery failed: answered with a 500, so Meta redelivers it and they are processed again."""

    status_code = 500
    code = "ingest_failed"


@dataclass
class InboxResult:
    processed: int = 0
    duplicates: int = 0
    ignored: int = 0
    failed: int = 0


class WhatsAppInbox:
    def __init__(self, db: AsyncClient, leads: LeadService, replies: ReplyService) -> None:
        self.events = IngestEventRepository(db)
        self.accounts = WhatsAppAccountRepository(db)
        self.leads = leads
        self.replies = replies

    async def handle(self, payload: object) -> InboxResult:
        """Process every message of one webhook delivery. Raises ``InboxError`` when any of them failed."""
        result = InboxResult()
        for message in parse_messages(payload):
            account = await self.accounts.get_by_phone_number_id(message.phone_number_id)
            if account is None:
                logger.fire("whatsapp_unknown_number", level="warning", phone_number_id=message.phone_number_id)
                result.ignored += 1
                continue
            event = await self.events.claim(account.business_id, SOURCE, message.message_id, message.kind, message.raw)
            if event is None:
                result.duplicates += 1
                continue
            try:
                status = await self._process(account, message)
            except Exception as exc:
                logger.fire(
                    "whatsapp_message_failed", level="error", _exc_info=exc, business_id=str(account.business_id),
                    message_id=message.message_id,
                )
                await self.events.finish(event, IngestStatus.FAILED, f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_LENGTH])
                result.failed += 1
                continue
            await self.events.finish(event, status)
            if status is IngestStatus.IGNORED:
                result.ignored += 1
            else:
                result.processed += 1
        logger.fire(
            "whatsapp_webhook_handled", level="warning" if result.failed else "info", processed=result.processed,
            duplicates=result.duplicates, ignored=result.ignored, failed=result.failed,
        )
        if result.failed:
            raise InboxError(f"{result.failed} WhatsApp message(s) failed")
        return result

    async def _process(self, account: WhatsAppAccount, message: WhatsAppMessage) -> IngestStatus:
        if message.kind in IGNORED_KINDS:
            return IngestStatus.IGNORED
        if message.sender == account.owner_phone:
            await self.replies.handle_owner_message(account, message)
            return IngestStatus.PROCESSED
        inbound = InboundChannelMessage(
            channel=Channel.WHATSAPP,
            message_id=message.message_id,
            phone=message.sender,
            sender_name=message.profile_name,
            body=message.text,
            kind=message.kind,
            sent_at=message.sent_at,
        )
        received = await self.leads.receive_message(account.business_id, inbound)
        return IngestStatus.PROCESSED if received else IngestStatus.IGNORED

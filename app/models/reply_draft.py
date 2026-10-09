import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from ai.schemas.enums import Channel


class ReplyDraftStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    AWAITING_EDIT = "awaiting_edit"  # the owner tapped Edit; their next message is the reply
    SENDING = "sending"  # approved and claimed by the process sending it
    SENT = "sent"
    REJECTED = "rejected"
    FAILED = "failed"  # sending failed; it may be approved again


# A draft in these states can still be approved, edited or rejected.
OPEN_DRAFT_STATUSES = frozenset({ReplyDraftStatus.PENDING_APPROVAL, ReplyDraftStatus.AWAITING_EDIT})
# ... and these may be claimed for sending (a failed send can be retried).
SENDABLE_DRAFT_STATUSES = OPEN_DRAFT_STATUSES | {ReplyDraftStatus.FAILED}


class DecisionChannel(StrEnum):
    """Where the owner decided: on their phone (the main surface) or the dashboard (the fallback)."""

    WHATSAPP = "whatsapp"
    DASHBOARD = "dashboard"


class ReplyDraft(BaseModel):
    """A `reply_drafts` row (db/001_core_tables.sql): an AI-drafted reply awaiting the owner (MAIN_PLAN §42)."""

    id: uuid.UUID
    business_id: uuid.UUID
    lead_id: uuid.UUID
    channel: Channel
    message: str
    objective: str | None
    status: ReplyDraftStatus
    edited: bool
    decided_via: DecisionChannel | None
    approval_message_id: str | None
    sent_message_id: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None
    sent_at: datetime | None

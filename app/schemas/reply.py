import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from ai.schemas.enums import Channel
from app.ingestion.normalize import Phone, normalize_phone
from app.models import DecisionChannel, ReplyDraftStatus

REPLY_MAX_LENGTH = 4096
MAX_AUTO_SEND_MINUTES = 24 * 60  # ck_whatsapp_accounts_auto_send_after_minutes


def _international[T: str | None](value: T) -> T:
    if value is not None and not value.startswith("+"):
        raise ValueError("use the international format with the country code, e.g. +972501234567")
    return value


InternationalPhone = Annotated[str, BeforeValidator(normalize_phone), AfterValidator(_international)]


class ReplyDraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    channel: Channel
    message: str
    objective: str | None
    status: ReplyDraftStatus
    edited: bool
    decided_via: DecisionChannel | None
    # Why the approval request or the reply could not be sent, if it could not.
    last_error: str | None
    created_at: datetime
    decided_at: datetime | None
    sent_at: datetime | None
    # When it is sent by itself if nobody decides first (null: it waits for a decision).
    auto_send_at: datetime | None = None
    # Only in the approval queue (``GET /replies``).
    lead_name: str | None = None


ReplyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REPLY_MAX_LENGTH)]


class ReplyApproval(BaseModel):
    """Approve a draft; ``message`` replaces its text (the owner edited it)."""

    model_config = ConfigDict(extra="forbid")

    message: ReplyText | None = None


class WhatsAppConnection(BaseModel):
    """``PUT /businesses/{id}/whatsapp``: the business's WhatsApp number and who approves its replies."""

    model_config = ConfigDict(extra="forbid")

    # Meta app > WhatsApp > API Setup > "Phone number ID" (not the phone number itself).
    phone_number_id: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{5,30}$")]
    display_phone: Annotated[Phone, AfterValidator(_international)] = None
    # The owner's own WhatsApp number: approval requests go there, and messages from it are decisions.
    owner_phone: InternationalPhone
    # A first reply the owner has not decided on within this many minutes is sent by itself; null: never.
    auto_send_after_minutes: int | None = Field(default=None, ge=1, le=MAX_AUTO_SEND_MINUTES)


class WhatsAppConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    phone_number_id: str
    display_phone: str | None
    owner_phone: str
    auto_send_after_minutes: int | None
    updated_at: datetime


class WhatsAppStatus(BaseModel):
    """The connection (None when not connected) and whether this deployment can send and receive at all."""

    connection: WhatsAppConnectionRead | None
    configured: bool
    webhook_path: str

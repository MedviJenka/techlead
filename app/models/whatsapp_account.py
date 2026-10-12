import uuid
from datetime import datetime

from pydantic import BaseModel


class WhatsAppAccount(BaseModel):
    """A `whatsapp_accounts` row (db/001_core_tables.sql): the business's WhatsApp number (MAIN_PLAN §66).

    Messages from ``owner_phone`` are the owner's approval decisions, never leads. A first reply the owner has not
    decided on within ``auto_send_after_minutes`` is sent by itself (None: it waits for the owner).
    """

    business_id: uuid.UUID
    phone_number_id: str
    display_phone: str | None
    owner_phone: str
    auto_send_after_minutes: int | None = None
    created_at: datetime
    updated_at: datetime

import uuid
from datetime import datetime

from pydantic import BaseModel


class WhatsAppAccount(BaseModel):
    """A `whatsapp_accounts` row (db/001_core_tables.sql): the business's WhatsApp number (MAIN_PLAN §66).

    Messages from ``owner_phone`` are the owner's approval decisions, never leads.
    """

    business_id: uuid.UUID
    phone_number_id: str
    display_phone: str | None
    owner_phone: str
    created_at: datetime
    updated_at: datetime

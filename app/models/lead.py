import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ai.schemas.enums import Priority, Sentiment


class Lead(BaseModel):
    """A `leads` row (db/001_core_tables.sql): a normalized lead (MAIN_PLAN §5); business data in `custom_fields`."""

    id: uuid.UUID
    business_id: uuid.UUID
    external_id: str | None
    source: str
    # Free-form because every business defines its own pipeline statuses (MAIN_PLAN §52).
    status: str
    priority: Priority | None
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    company_name: str | None
    notes: str | None
    lead_score: int | None
    sentiment: Sentiment | None
    ai_summary: str | None
    recommended_action: str | None
    custom_fields: dict[str, Any]
    raw_payload: dict[str, Any]
    last_contact_at: datetime | None
    created_at: datetime
    updated_at: datetime

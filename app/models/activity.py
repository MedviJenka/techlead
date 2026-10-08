import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ai.schemas.enums import ActivityType, Channel


class Activity(BaseModel):
    """An `activities` row (db/001_core_tables.sql): append-only lead event (MAIN_PLAN §6), never updated."""

    id: uuid.UUID
    business_id: uuid.UUID
    lead_id: uuid.UUID
    activity_type: ActivityType
    channel: Channel | None
    description: str
    metadata: dict[str, Any]
    created_at: datetime

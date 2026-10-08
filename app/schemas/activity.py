import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ai.schemas.enums import ActivityType, Channel


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    activity_type: ActivityType
    channel: Channel | None
    description: str
    metadata: dict[str, Any]
    created_at: datetime

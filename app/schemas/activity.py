import uuid
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from ai.schemas.enums import ActivityType, Channel


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    activity_type: ActivityType
    channel: Channel | None
    description: str
    # The ORM attribute is `metadata_` (`metadata` is reserved on declarative classes); `metadata_` is tried
    # first so the class-level SQLAlchemy MetaData is never picked up. Serialized as `metadata`.
    metadata: dict[str, Any] = Field(validation_alias=AliasChoices("metadata_", "metadata"))
    created_at: datetime

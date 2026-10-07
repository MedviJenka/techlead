import uuid
from datetime import datetime
from typing import Any
from zoneinfo import available_timezones
from pydantic import BaseModel, ConfigDict, Field, field_validator
from ai.schemas.business import AIConfiguration


SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class BusinessCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=SLUG_PATTERN)
    industry: str | None = Field(default=None, max_length=100)
    timezone: str = "UTC"
    configuration: dict[str, Any] = Field(default_factory=dict)
    custom_field_definitions: list[dict[str, Any]] = Field(default_factory=list)
    ai_configuration: AIConfiguration = Field(default_factory=AIConfiguration)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            raise ValueError(f"unknown IANA timezone: {value}")
        return value


class BusinessRead(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    industry: str | None
    timezone: str
    configuration: dict[str, Any]
    custom_field_definitions: list[dict[str, Any]]
    ai_configuration: AIConfiguration
    created_at: datetime
    updated_at: datetime

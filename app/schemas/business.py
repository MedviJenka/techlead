import uuid
from datetime import datetime
from typing import Annotated, Any
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationInfo, field_validator

from ai.schemas.business import AIConfiguration
from app.schemas.common import MAX_JSON_FIELD_BYTES as MAX_JSON_FIELD_BYTES  # re-export (backward compat)
from app.schemas.common import check_json_size

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

# Computed once: available_timezones() walks the tzdata tree on every call.
KNOWN_TIMEZONES: frozenset[str] = frozenset(available_timezones())

# Cap for list entries on the public create endpoint (the JSON byte cap is MAX_JSON_FIELD_BYTES, re-exported).
MAX_CUSTOM_FIELD_DEFINITIONS = 100

MAX_EXTRA_SKILLS = 10
SkillName = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=SLUG_PATTERN)]


class AIConfigurationInput(BaseModel):
    """Client-settable subset of ``AIConfiguration``.

    Policy fields (autonomy_level, allowed_actions, approval_required_actions) are deliberately absent: they
    stay at the server-side ``AIConfiguration`` defaults until changing them is a separately authorized action.
    """

    model_config = ConfigDict(extra="forbid")

    tone: str = Field(default="professional, warm and concise", min_length=1, max_length=200)
    language: str = Field(default="English", min_length=1, max_length=50)
    instructions: str | None = Field(default=None, max_length=4000)
    # TODO: validate names against the skill library once it is importable without crewai; unknown names
    # currently surface only at crew composition (ai/factory/skills.py).
    extra_skills: list[SkillName] = Field(default_factory=list, max_length=MAX_EXTRA_SKILLS)

    def to_ai_configuration(self) -> AIConfiguration:
        """Full AI configuration with server-controlled policy defaults applied."""
        return AIConfiguration(**self.model_dump())


class BusinessCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=SLUG_PATTERN)
    industry: str | None = Field(default=None, max_length=100)
    timezone: str = "UTC"
    configuration: dict[str, Any] = Field(default_factory=dict)
    custom_field_definitions: list[dict[str, Any]] = Field(
        default_factory=list, max_length=MAX_CUSTOM_FIELD_DEFINITIONS
    )
    ai_configuration: AIConfigurationInput = Field(default_factory=AIConfigurationInput)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        if value not in KNOWN_TIMEZONES:
            raise ValueError(f"unknown IANA timezone: {value}")
        return value

    @field_validator("configuration", "custom_field_definitions")
    @classmethod
    def _bounded_json(cls, value: Any, info: ValidationInfo) -> Any:
        return check_json_size(value, info.field_name or "value")


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

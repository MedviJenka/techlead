import uuid
from datetime import datetime
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator

from ai.schemas.business import AIConfiguration
from app.schemas.common import MAX_JSON_FIELD_BYTES as MAX_JSON_FIELD_BYTES  # re-export (backward compat)
from app.schemas.configuration import (
    MAX_CUSTOM_FIELD_DEFINITIONS,
    BusinessConfiguration,
    CustomFieldDefinition,
    check_unique_keys,
    stored_definitions,
)

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

# Computed once: available_timezones() walks the tzdata tree on every call.
KNOWN_TIMEZONES: frozenset[str] = frozenset(available_timezones())

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
    configuration: BusinessConfiguration = Field(default_factory=BusinessConfiguration)
    custom_field_definitions: list[CustomFieldDefinition] = Field(
        default_factory=list, max_length=MAX_CUSTOM_FIELD_DEFINITIONS
    )
    ai_configuration: AIConfigurationInput = Field(default_factory=AIConfigurationInput)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        if value not in KNOWN_TIMEZONES:
            raise ValueError(f"unknown IANA timezone: {value}")
        return value

    @field_validator("custom_field_definitions")
    @classmethod
    def _unique_keys(cls, value: list[CustomFieldDefinition]) -> list[CustomFieldDefinition]:
        return check_unique_keys(value)


class BusinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    industry: str | None
    timezone: str
    # Effective settings: stored values that do not parse read as the defaults.
    configuration: Annotated[BusinessConfiguration, BeforeValidator(BusinessConfiguration.from_stored)]
    custom_field_definitions: Annotated[list[CustomFieldDefinition], BeforeValidator(stored_definitions)]
    ai_configuration: AIConfiguration
    created_at: datetime
    updated_at: datetime

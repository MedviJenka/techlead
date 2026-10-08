"""Lead contracts. Inputs normalize through ``app.ingestion.normalize`` so API and import data are identical."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from ai.schemas.enums import Priority, Sentiment
from app.ingestion.normalize import (
    Email,
    LongText,
    OptionalToken50,
    Phone,
    PriorityValue,
    Score,
    SentimentValue,
    Text50,
    Text100,
    Text200,
    Text255,
    Token50,
    UtcDatetime,
)
from app.schemas.common import check_json_size

DEFAULT_PAGE_LIMIT = 25
MAX_PAGE_LIMIT = 100
MAX_PAGE_OFFSET = 10_000
MAX_QUERY_LENGTH = 100


class LeadCreate(BaseModel):
    """Manual lead creation. AI fields, ``created_at`` and ``raw_payload`` are not client-settable.

    ``status``/``priority`` default to ``None``: the ``"new"`` status is applied only when inserting, so a later
    merge without a status never resets one.
    """

    model_config = ConfigDict(extra="forbid")

    source: Token50
    external_id: Text255 = None
    status: OptionalToken50 = None
    priority: PriorityValue = None
    first_name: Text100 = None
    last_name: Text100 = None
    email: Email = None
    phone: Phone = None
    company_name: Text200 = None
    notes: LongText = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    last_contact_at: UtcDatetime = None

    @field_validator("custom_fields")
    @classmethod
    def _bounded_custom_fields(cls, value: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        check_json_size(value, info.field_name or "custom_fields")
        return value


class LeadImportData(LeadCreate):
    """A lead as produced by an ingestion adapter: adds the source timestamp and upstream AI fields."""

    created_at: UtcDatetime = None
    lead_score: Score | None = None
    sentiment: SentimentValue = None
    ai_summary: LongText = None
    recommended_action: Text50 = None


class LeadUpdate(BaseModel):
    """PATCH body; apply with ``model_dump(exclude_unset=True)``. ``custom_fields`` replaces the stored dict."""

    model_config = ConfigDict(extra="forbid")

    status: OptionalToken50 = None
    priority: PriorityValue = None
    first_name: Text100 = None
    last_name: Text100 = None
    email: Email = None
    phone: Phone = None
    company_name: Text200 = None
    notes: LongText = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    last_contact_at: UtcDatetime = None

    @field_validator("status")
    @classmethod
    def _status_not_null(cls, value: str | None) -> str | None:
        # Only runs for explicitly sent values (defaults are not validated), so omitting status is fine.
        if value is None:
            raise ValueError("status cannot be null")
        return value

    @field_validator("custom_fields")
    @classmethod
    def _bounded_custom_fields(cls, value: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        check_json_size(value, info.field_name or "custom_fields")
        return value


class LeadListParams(BaseModel):
    """Query parameters of ``GET /leads``; filters are AND-combined."""

    model_config = ConfigDict(extra="forbid")

    status: OptionalToken50 = None
    priority: PriorityValue = None
    source: OptionalToken50 = None
    q: str | None = Field(default=None, min_length=1, max_length=MAX_QUERY_LENGTH)
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    offset: int = Field(default=0, ge=0, le=MAX_PAGE_OFFSET)


class LeadSummary(BaseModel):
    """List/table view of a lead. ``business_id`` is in the URL; ``raw_payload`` is never returned."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str | None
    source: str
    status: str
    priority: Priority | None
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    company_name: str | None
    lead_score: int | None
    sentiment: Sentiment | None
    recommended_action: str | None
    last_contact_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LeadRead(LeadSummary):
    notes: str | None
    ai_summary: str | None
    custom_fields: dict[str, Any]

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Business(BaseModel):
    """A `businesses` row (db/001_core_tables.sql): a tenant. Per-business behaviour lives in JSONB (MAIN_PLAN §4)."""

    id: uuid.UUID
    name: str
    slug: str
    industry: str | None
    timezone: str
    configuration: dict[str, Any]
    custom_field_definitions: list[dict[str, Any]]
    ai_configuration: dict[str, Any]
    created_at: datetime
    updated_at: datetime

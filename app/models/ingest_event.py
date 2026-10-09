import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class IngestStatus(StrEnum):
    PROCESSING = "processing"
    PROCESSED = "processed"
    IGNORED = "ignored"  # recorded, but nothing to do (e.g. an unsupported message type)
    FAILED = "failed"  # a redelivery processes it again


class IngestEvent(BaseModel):
    """An `ingest_events` row (db/001_core_tables.sql): one inbound webhook event, processed once (MAIN_PLAN §59)."""

    id: uuid.UUID
    business_id: uuid.UUID
    source: str
    external_event_id: str
    event_type: str
    status: IngestStatus
    attempts: int
    payload: dict[str, Any]
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None

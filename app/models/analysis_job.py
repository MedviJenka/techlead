import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class AnalysisJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AnalysisTrigger(StrEnum):
    LEAD_CREATED = "lead_created"
    MANUAL = "manual"


class AnalysisJob(BaseModel):
    """An `analysis_jobs` row (db/001_core_tables.sql): one AI run of NewLeadFlow on a lead (MAIN_PLAN §58, §65)."""

    id: uuid.UUID
    business_id: uuid.UUID
    lead_id: uuid.UUID
    trigger: AnalysisTrigger
    status: AnalysisJobStatus
    attempts: int
    max_attempts: int
    run_after: datetime
    locked_until: datetime | None
    worker: str | None
    last_error: str | None
    usage: dict[str, Any] | None
    cost_usd: Decimal | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None

    @property
    def open(self) -> bool:
        return self.status in (AnalysisJobStatus.PENDING, AnalysisJobStatus.RUNNING)

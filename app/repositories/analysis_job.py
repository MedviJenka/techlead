import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from supabase import AsyncClient

from app.core.supabase import to_json
from app.models import AnalysisJob, AnalysisJobStatus, AnalysisTrigger


class AnalysisJobRepository:
    """The AI job queue (MAIN_PLAN §58). Enqueue and claim are database functions (db/004_functions.sql).

    A worker's writes match ``worker`` and ``status = running``: once its lease expired and another worker claimed
    the job, the late writes of the first one change nothing.
    """

    def __init__(self, db: AsyncClient) -> None:
        self._db = db

    async def enqueue(self, business_id: uuid.UUID, lead_id: uuid.UUID, trigger: AnalysisTrigger) -> AnalysisJob:
        """The lead's open job, created if there is none (so a double click runs the crew once)."""
        params = {"p_business_id": str(business_id), "p_lead_id": str(lead_id), "p_trigger": trigger.value}
        response = await self._db.rpc("enqueue_analysis", params).execute()
        return AnalysisJob.model_validate(response.data)

    async def claim(self, worker: str, lease_seconds: int) -> AnalysisJob | None:
        """Lease the next due job to ``worker``; None when nothing is due."""
        params = {"p_worker": worker, "p_lease_seconds": lease_seconds}
        response = await self._db.rpc("claim_analysis_job", params).execute()
        rows = cast(list[dict[str, Any]], response.data or [])
        return AnalysisJob.model_validate(rows[0]) if rows else None

    async def latest_for_lead(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> AnalysisJob | None:
        response = (
            await self._db.table("analysis_jobs")
            .select("*")
            .eq("business_id", str(business_id))
            .eq("lead_id", str(lead_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return AnalysisJob.model_validate(response.data[0]) if response.data else None

    async def succeed(self, job: AnalysisJob, usage: dict[str, Any] | None, cost_usd: Decimal | None) -> bool:
        now = datetime.now(UTC)
        values = {"status": AnalysisJobStatus.SUCCEEDED, "usage": usage, "cost_usd": cost_usd, "last_error": None}
        return await self._finish(job, values | {"finished_at": now, "locked_until": None})

    async def retry(self, job: AnalysisJob, error: str, run_after: datetime) -> bool:
        values = {"status": AnalysisJobStatus.PENDING, "last_error": error, "run_after": run_after}
        return await self._finish(job, values | {"locked_until": None})

    async def fail(self, job: AnalysisJob, error: str) -> bool:
        values = {"status": AnalysisJobStatus.FAILED, "last_error": error, "finished_at": datetime.now(UTC)}
        return await self._finish(job, values | {"locked_until": None})

    async def _finish(self, job: AnalysisJob, values: dict[str, Any]) -> bool:
        """True when this worker still held the job and the row was updated."""
        response = (
            await self._db.table("analysis_jobs")
            .update(to_json(values | {"updated_at": datetime.now(UTC)}))
            .eq("id", str(job.id))
            .eq("status", AnalysisJobStatus.RUNNING.value)
            .eq("worker", job.worker or "")
            .execute()
        )
        return bool(response.data)

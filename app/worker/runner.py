"""The AI worker: claims analysis jobs and runs NewLeadFlow on them (MAIN_PLAN §58, §65).

A failed run is retried with exponential backoff until ``max_attempts``; the lead itself is never touched by a
failure. A worker that dies mid-run leaves its job ``running`` until the lease expires; another worker then takes
it over (that counts as an attempt).
"""

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from app.analysis.flow import FlowOutcome
from app.core.errors import NotFoundError
from app.core.logger import Logger
from app.models import AnalysisJob

logger = Logger(__name__)

_MAX_ERROR_LENGTH = 2000


class JobQueue(Protocol):
    async def claim(self, worker: str, lease_seconds: int) -> AnalysisJob | None: ...

    async def succeed(self, job: AnalysisJob, usage: dict[str, Any] | None, cost_usd: Decimal | None) -> bool: ...

    async def retry(self, job: AnalysisJob, error: str, run_after: datetime) -> bool: ...

    async def fail(self, job: AnalysisJob, error: str) -> bool: ...


class Flow(Protocol):
    async def run(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> FlowOutcome: ...


@dataclass(frozen=True)
class RetryPolicy:
    base_seconds: float = 30.0
    max_seconds: float = 3600.0

    def delay(self, attempts: int) -> timedelta:
        """30s, 60s, 120s, ... capped at ``max_seconds`` (``attempts`` counts the run that just failed)."""
        return timedelta(seconds=min(self.base_seconds * 2 ** max(attempts - 1, 0), self.max_seconds))


_DEFAULT_RETRY = RetryPolicy()


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_LENGTH]


class AnalysisWorker:
    """``make_flow(now)`` builds the flow for one job, with a service whose clock is the job's start time."""

    def __init__(
        self,
        jobs: JobQueue,
        make_flow: Callable[[datetime], Flow],
        clock: Callable[[], datetime],
        *,
        name: str,
        lease_seconds: int = 900,
        retry: RetryPolicy = _DEFAULT_RETRY,
    ) -> None:
        self._jobs = jobs
        self._make_flow = make_flow
        self._clock = clock
        self.name = name
        self._lease = lease_seconds
        self._retry = retry

    async def run_once(self) -> bool:
        """Process one due job. False when there was none."""
        job = await self._jobs.claim(self.name, self._lease)
        if job is None:
            return False
        log: dict[str, Any] = {"job_id": str(job.id), "business_id": str(job.business_id), "lead_id": str(job.lead_id)}
        if job.attempts > job.max_attempts:  # a worker died on its last attempt: the lease expired, give up
            await self._jobs.fail(job, job.last_error or "Worker stopped during the last attempt")
            logger.fire("analysis_job_abandoned", level="error", attempts=job.attempts, **log)
            return True
        logger.fire("analysis_job_started", attempt=job.attempts, trigger=job.trigger.value, **log)
        now = self._clock()
        try:
            outcome = await self._make_flow(now).run(job.business_id, job.lead_id)
        except NotFoundError as exc:  # the lead or business was deleted: nothing left to analyse
            await self._jobs.fail(job, _describe(exc))
            logger.fire("analysis_job_dropped", level="warning", reason=str(exc), **log)
        except Exception as exc:
            await self._failed(job, exc, now, log)
        else:
            cost = outcome.cost
            usage = cost.as_metadata() if cost else None
            stored = await self._jobs.succeed(job, usage, cost.cost_usd if cost else None)
            logger.fire(
                "analysis_job_succeeded" if stored else "analysis_job_lease_lost",
                level="info" if stored else "warning",
                route=outcome.route.value,
                **log,
            )
        return True

    async def _failed(self, job: AnalysisJob, exc: Exception, now: datetime, log: dict[str, Any]) -> None:
        error = _describe(exc)
        if job.attempts >= job.max_attempts:
            await self._jobs.fail(job, error)
            logger.fire("analysis_job_failed", level="error", _exc_info=exc, attempts=job.attempts, **log)
            return
        run_after = now + self._retry.delay(job.attempts)
        await self._jobs.retry(job, error, run_after)
        logger.fire(
            "analysis_job_retry", level="warning", _exc_info=exc, attempts=job.attempts,
            run_after=run_after.isoformat(), **log,
        )

    async def run(self, stop: asyncio.Event, idle_seconds: float = 2.0, error_seconds: float = 10.0) -> None:
        """Process jobs until ``stop`` is set; sleep ``idle_seconds`` when none is due.

        A job in progress finishes before the worker stops. A database outage pauses the loop, never ends it.
        """
        logger.fire("worker_started", worker=self.name)
        while not stop.is_set():
            try:
                busy = await self.run_once()
            except Exception as exc:
                logger.fire("worker_loop_error", level="error", _exc_info=exc, worker=self.name)
                busy, wait = False, error_seconds
            else:
                wait = idle_seconds
            if not busy:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=wait)
                except TimeoutError:
                    pass
        logger.fire("worker_stopped", worker=self.name)

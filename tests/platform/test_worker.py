"""The AI worker (app/worker) on the in-memory job queue: success, retry with backoff, give-up, lease takeover."""

import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.analysis.flow import FlowOutcome, LeadRoute
from app.core.errors import NotFoundError
from app.models import AnalysisJob, AnalysisJobStatus, AnalysisTrigger
from app.schemas.analysis import RunCost
from app.worker.runner import AnalysisWorker, RetryPolicy
from tests.platform.memory import NOW, FakeJobs

BUSINESS_ID, LEAD_ID = uuid.uuid4(), uuid.uuid4()
COST = RunCost("openai/test", 1000, 0, 100, 3, Decimal("0.002250"))


class FakeFlow:
    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.runs: list[tuple[uuid.UUID, uuid.UUID, datetime]] = []
        self.now = NOW

    async def run(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> FlowOutcome:
        self.runs.append((business_id, lead_id, self.now))
        if self.errors:
            raise self.errors.pop(0)
        return FlowOutcome(lead=None, route=LeadRoute.HOT, cost=COST)  # type: ignore[arg-type]


@pytest.fixture
def jobs() -> FakeJobs:
    return FakeJobs()


def _worker(jobs: FakeJobs, flow: FakeFlow, name: str = "w1") -> AnalysisWorker:
    def make_flow(now: datetime) -> FakeFlow:
        flow.now = now
        return flow

    retry = RetryPolicy(base_seconds=30, max_seconds=100)
    return AnalysisWorker(jobs, make_flow, lambda: jobs.clock, name=name, lease_seconds=600, retry=retry)


async def _job(jobs: FakeJobs) -> AnalysisJob:
    return await jobs.enqueue(BUSINESS_ID, LEAD_ID, AnalysisTrigger.LEAD_CREATED)


def _current(jobs: FakeJobs) -> AnalysisJob:
    return jobs.jobs[-1]


async def test_no_due_job_means_no_work(jobs: FakeJobs) -> None:
    assert await _worker(jobs, FakeFlow()).run_once() is False


async def test_success_records_usage_and_cost(jobs: FakeJobs) -> None:
    await _job(jobs)
    flow = FakeFlow()

    assert await _worker(jobs, flow).run_once() is True

    job = _current(jobs)
    assert flow.runs == [(BUSINESS_ID, LEAD_ID, NOW)]
    assert (job.status, job.attempts, job.cost_usd, job.finished_at) == (
        AnalysisJobStatus.SUCCEEDED, 1, Decimal("0.002250"), NOW
    )
    assert job.usage is not None and job.usage["prompt_tokens"] == 1000


async def test_failure_is_retried_with_exponential_backoff_then_given_up(jobs: FakeJobs) -> None:
    await _job(jobs)
    flow = FakeFlow(*[TimeoutError("LLM timed out")] * 5)
    worker = _worker(jobs, flow)

    delays = []
    for _ in range(4):
        await worker.run_once()
        job = _current(jobs)
        assert job.status is AnalysisJobStatus.PENDING and job.last_error == "TimeoutError: LLM timed out"
        delays.append(job.run_after - jobs.clock)
        assert await worker.run_once() is False  # not due yet
        jobs.clock = job.run_after
    assert delays == [timedelta(seconds=s) for s in (30, 60, 100, 100)]  # capped at max_seconds

    await worker.run_once()  # 5th attempt = max_attempts

    job = _current(jobs)
    assert (job.status, job.attempts) == (AnalysisJobStatus.FAILED, 5)
    assert len(flow.runs) == 5


async def test_a_deleted_lead_fails_the_job_without_retrying(jobs: FakeJobs) -> None:
    await _job(jobs)

    await _worker(jobs, FakeFlow(NotFoundError("Lead not found"))).run_once()

    assert (_current(jobs).status, _current(jobs).attempts) == (AnalysisJobStatus.FAILED, 1)


async def test_a_crashed_workers_job_is_taken_over_after_its_lease(jobs: FakeJobs) -> None:
    await _job(jobs)
    crashed = await jobs.claim("crashed", 600)  # claimed, then the process died
    assert crashed is not None
    flow = FakeFlow()
    worker = _worker(jobs, flow, name="w2")

    assert await worker.run_once() is False  # lease still valid
    jobs.clock += timedelta(seconds=601)
    assert await worker.run_once() is True

    job = _current(jobs)
    assert (job.status, job.attempts, job.worker) == (AnalysisJobStatus.SUCCEEDED, 2, "w2")
    # The crashed worker's late write changes nothing.
    assert await jobs.fail(crashed, "late") is False and _current(jobs).status is AnalysisJobStatus.SUCCEEDED


async def test_a_job_whose_worker_died_on_the_last_attempt_is_abandoned(jobs: FakeJobs) -> None:
    await _job(jobs)
    jobs.jobs[-1] = _current(jobs).model_copy(update={"attempts": 5, "last_error": "TimeoutError: slow"})
    await jobs.claim("crashed", 600)
    jobs.clock += timedelta(seconds=601)
    flow = FakeFlow()

    await _worker(jobs, flow).run_once()

    job = _current(jobs)
    assert (job.status, job.last_error, flow.runs) == (AnalysisJobStatus.FAILED, "TimeoutError: slow", [])


async def test_run_stops_when_asked_and_survives_queue_errors(jobs: FakeJobs) -> None:
    calls = 0

    async def claim(worker: str, lease_seconds: int) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("database unreachable")
        stop.set()
        return None

    jobs.claim = claim  # type: ignore[method-assign]
    stop = asyncio.Event()

    await asyncio.wait_for(_worker(jobs, FakeFlow()).run(stop, idle_seconds=0, error_seconds=0), timeout=2)

    assert calls == 2

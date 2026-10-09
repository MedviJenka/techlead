"""db/004_functions.sql on the test Supabase project: atomic lead save, the job queue and the business lease."""

import uuid

import pytest
from postgrest.exceptions import APIError
from supabase import AsyncClient

from ai.schemas.enums import ActivityType
from app.core.locks import DatabaseBusinessLock
from app.models import AnalysisJobStatus, AnalysisTrigger
from app.repositories import ActivityRepository, LeadRepository
from app.repositories.analysis_job import AnalysisJobRepository
from tests.platform.factories import make_business

CREATED = {"activity_type": ActivityType.LEAD_CREATED, "description": "Lead created", "metadata": {}}
SCORED = {"activity_type": ActivityType.SCORE_CHANGED, "description": "Lead score changed", "metadata": {"to": 40}}


async def test_save_lead_writes_lead_activities_and_job_together(db: AsyncClient) -> None:
    business = await make_business(db)
    leads, activities, jobs = LeadRepository(db), ActivityRepository(db), AnalysisJobRepository(db)

    lead = await leads.save(
        business.id, None, {"source": "web", "first_name": "Dana"}, [CREATED, SCORED], AnalysisTrigger.LEAD_CREATED
    )

    assert (lead.first_name, lead.status, lead.custom_fields) == ("Dana", "new", {})
    timeline = await activities.all_for_lead(business.id, lead.id)
    assert [a.activity_type for a in timeline] == [ActivityType.LEAD_CREATED, ActivityType.SCORE_CHANGED]
    job = await jobs.latest_for_lead(business.id, lead.id)
    assert job is not None and (job.status, job.trigger) == (AnalysisJobStatus.PENDING, AnalysisTrigger.LEAD_CREATED)


async def test_a_failed_activity_leaves_no_lead_behind(db: AsyncClient) -> None:
    business = await make_business(db)
    bad = {"activity_type": "not_a_type", "description": "x", "metadata": {}}

    with pytest.raises(APIError, match="ck_activities_activity_type"):
        await LeadRepository(db).save(business.id, None, {"source": "web"}, [CREATED, bad])

    assert (await db.table("leads").select("id").eq("business_id", str(business.id)).execute()).data == []


async def test_updating_a_missing_lead_is_a_lookup_error(db: AsyncClient) -> None:
    business = await make_business(db)

    with pytest.raises(LookupError):
        await LeadRepository(db).save(business.id, uuid.uuid4(), {"notes": "x"}, [])


async def test_queue_keeps_one_open_job_per_lead_and_leases_it_once(db: AsyncClient) -> None:
    business = await make_business(db)
    lead = await LeadRepository(db).save(business.id, None, {"source": "web"}, [CREATED])
    jobs = AnalysisJobRepository(db)

    first = await jobs.enqueue(business.id, lead.id, AnalysisTrigger.MANUAL)
    again = await jobs.enqueue(business.id, lead.id, AnalysisTrigger.MANUAL)
    claimed = await jobs.claim("w1", 600)

    assert again.id == first.id
    assert claimed is not None and (claimed.id, claimed.attempts, claimed.worker) == (first.id, 1, "w1")
    assert await jobs.claim("w2", 600) is None
    assert await jobs.succeed(claimed, {"requests": 3}, None) is True
    assert (await jobs.enqueue(business.id, lead.id, AnalysisTrigger.MANUAL)).id != first.id  # closed: a new run


async def test_business_lease_excludes_a_second_holder(db: AsyncClient) -> None:
    business = await make_business(db)
    lock = DatabaseBusinessLock(db, wait_seconds=0.5, poll_seconds=0.1)
    params = {"p_business_id": str(business.id), "p_holder": "someone-else", "p_ttl_seconds": 30}

    async with lock.hold(business.id):
        assert (await db.rpc("try_lock_business", params).execute()).data is not True

    assert (await db.rpc("try_lock_business", params).execute()).data is True

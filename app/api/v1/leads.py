import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DashboardServiceDep, LeadServiceDep
from app.core.clock import utc_now as utc_now  # re-export: tests override this dependency
from app.intelligence import ScoreBreakdown
from app.schemas.activity import ActivityRead
from app.schemas.analysis import AnalysisJobRead, LeadAnalysisState
from app.schemas.common import Page
from app.schemas.dashboard import DashboardSummary
from app.schemas.lead import LeadCreate, LeadListItem, LeadListParams, LeadRead, LeadUpdate, RescoreResult
from app.schemas.lead_import import ImportEnvelope, ImportResult

router = APIRouter(prefix="/businesses/{business_id}", tags=["leads"])


@router.get("/leads", response_model=Page[LeadListItem])
async def list_leads(
    business_id: uuid.UUID, service: LeadServiceDep, params: Annotated[LeadListParams, Query()]
) -> Page[LeadListItem]:
    return await service.list(business_id, params)


@router.post("/leads", response_model=LeadRead)
async def create_lead(business_id: uuid.UUID, payload: LeadCreate, service: LeadServiceDep) -> LeadRead:
    return await service.read(await service.create(business_id, payload))


@router.post("/leads/import", response_model=ImportResult)
async def import_leads(business_id: uuid.UUID, payload: ImportEnvelope, service: LeadServiceDep) -> ImportResult:
    return await service.import_batch(business_id, payload)


@router.post("/leads/rescore", response_model=RescoreResult)
async def rescore_leads(business_id: uuid.UUID, service: LeadServiceDep) -> RescoreResult:
    return await service.rescore(business_id)


@router.get("/leads/{lead_id}", response_model=LeadRead)
async def get_lead(business_id: uuid.UUID, lead_id: uuid.UUID, service: LeadServiceDep) -> LeadRead:
    return await service.read(await service.get(business_id, lead_id))


@router.patch("/leads/{lead_id}", response_model=LeadRead)
async def update_lead(
    business_id: uuid.UUID, lead_id: uuid.UUID, payload: LeadUpdate, service: LeadServiceDep
) -> LeadRead:
    return await service.read(await service.update(business_id, lead_id, payload))


@router.get("/leads/{lead_id}/score", response_model=ScoreBreakdown)
async def lead_score(business_id: uuid.UUID, lead_id: uuid.UUID, service: LeadServiceDep) -> ScoreBreakdown:
    return await service.score(business_id, lead_id)


@router.post("/leads/{lead_id}/analyze", response_model=AnalysisJobRead, status_code=status.HTTP_202_ACCEPTED)
async def analyze_lead(business_id: uuid.UUID, lead_id: uuid.UUID, service: LeadServiceDep) -> AnalysisJobRead:
    """Queue the AI analysis (NewLeadFlow) for the worker and return its job at once (``analysis_pending``).

    Poll ``GET .../analysis`` until the job is ``succeeded`` or ``failed``. Asking again while a job is open
    returns that job.
    """
    job = await service.request_analysis(business_id, lead_id)
    return AnalysisJobRead.model_validate(job.model_dump())


@router.get("/leads/{lead_id}/analysis", response_model=LeadAnalysisState)
async def lead_analysis(business_id: uuid.UUID, lead_id: uuid.UUID, service: LeadServiceDep) -> LeadAnalysisState:
    return await service.analysis_state(business_id, lead_id)


@router.get("/leads/{lead_id}/activities", response_model=Page[ActivityRead])
async def lead_activities(
    business_id: uuid.UUID,
    lead_id: uuid.UUID,
    service: LeadServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> Page[ActivityRead]:
    return await service.timeline(business_id, lead_id, limit, offset)


@router.get("/dashboard", response_model=DashboardSummary)
async def dashboard(
    business_id: uuid.UUID, service: DashboardServiceDep, now: Annotated[datetime, Depends(utc_now)]
) -> DashboardSummary:
    return await service.summary(business_id, now)

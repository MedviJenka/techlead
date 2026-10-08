import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DashboardServiceDep, LeadServiceDep
from app.models import Lead
from app.schemas.activity import ActivityRead
from app.schemas.common import Page
from app.schemas.dashboard import DashboardSummary
from app.schemas.lead import LeadCreate, LeadListParams, LeadRead, LeadSummary, LeadUpdate
from app.schemas.lead_import import ImportEnvelope, ImportResult

router = APIRouter(prefix="/businesses/{business_id}", tags=["leads"])


def utc_now() -> datetime:
    return datetime.now(UTC)


@router.get("/leads", response_model=Page[LeadSummary])
async def list_leads(
    business_id: uuid.UUID,
    service: LeadServiceDep,
    params: Annotated[LeadListParams, Query()],
) -> Page[LeadSummary]:
    return await service.list(business_id, params)


@router.post("/leads", response_model=LeadRead)
async def create_lead(business_id: uuid.UUID, payload: LeadCreate, service: LeadServiceDep) -> Lead:
    return await service.create(business_id, payload)


@router.post("/leads/import", response_model=ImportResult)
async def import_leads(business_id: uuid.UUID, payload: ImportEnvelope, service: LeadServiceDep) -> ImportResult:
    return await service.import_batch(business_id, payload)


@router.get("/leads/{lead_id}", response_model=LeadRead)
async def get_lead(business_id: uuid.UUID, lead_id: uuid.UUID, service: LeadServiceDep) -> Lead:
    return await service.get(business_id, lead_id)


@router.patch("/leads/{lead_id}", response_model=LeadRead)
async def update_lead(business_id: uuid.UUID, lead_id: uuid.UUID, payload: LeadUpdate, service: LeadServiceDep) -> Lead:
    return await service.update(business_id, lead_id, payload)


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
    business_id: uuid.UUID,
    service: DashboardServiceDep,
    now: Annotated[datetime, Depends(utc_now)],
) -> DashboardSummary:
    return await service.summary(business_id, now)

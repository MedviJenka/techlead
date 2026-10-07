import uuid

from fastapi import APIRouter, status

from app.api.deps import BusinessServiceDep
from app.models import Business
from app.schemas import BusinessCreate, BusinessRead

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.post("", response_model=BusinessRead, status_code=status.HTTP_201_CREATED)
async def create_business(payload: BusinessCreate, service: BusinessServiceDep) -> Business:
    return await service.create(payload)


@router.get("/{business_id}", response_model=BusinessRead)
async def get_business(business_id: uuid.UUID, service: BusinessServiceDep) -> Business:
    return await service.get(business_id)

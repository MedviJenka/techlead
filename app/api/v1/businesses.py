import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import AccountServiceDep, BusinessServiceDep, require_business_access
from app.core.auth import CurrentUser
from app.models import Business
from app.schemas import BusinessCreate, BusinessRead

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.post("", response_model=BusinessRead, status_code=status.HTTP_201_CREATED)
async def create_business(payload: BusinessCreate, user: CurrentUser, service: AccountServiceDep) -> Business:
    return await service.create_business(user, payload)


@router.get("/{business_id}", response_model=BusinessRead, dependencies=[Depends(require_business_access)])
async def get_business(business_id: uuid.UUID, service: BusinessServiceDep) -> Business:
    return await service.get(business_id)

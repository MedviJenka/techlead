import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import AccountServiceDep, BusinessServiceDep, require_business_access
from app.core.auth import CurrentUser
from app.models import Business
from app.schemas import BusinessCreate, BusinessRead
from app.schemas.configuration import BusinessSettingsUpdate

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.post("", response_model=BusinessRead, status_code=status.HTTP_201_CREATED)
async def create_business(payload: BusinessCreate, user: CurrentUser, service: AccountServiceDep) -> Business:
    return await service.create_business(user, payload)


@router.get("/{business_id}", response_model=BusinessRead, dependencies=[Depends(require_business_access)])
async def get_business(business_id: uuid.UUID, service: BusinessServiceDep) -> Business:
    return await service.get(business_id)


@router.put("/{business_id}/settings", response_model=BusinessRead, dependencies=[Depends(require_business_access)])
async def update_business_settings(
    business_id: uuid.UUID, payload: BusinessSettingsUpdate, service: BusinessServiceDep
) -> Business:
    """Replace configuration and custom field definitions. Call ``POST .../leads/rescore`` to apply new scoring."""
    return await service.update_settings(business_id, payload)

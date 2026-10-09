import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import AccountServiceDep, BusinessServiceDep, require_business_access
from app.core.auth import CurrentUser
from app.models import Business
from app.presets import PRESETS
from app.schemas import BusinessCreate, BusinessRead
from app.schemas.business import PresetRead
from app.schemas.configuration import BusinessSettingsUpdate

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("/presets", response_model=list[PresetRead])
async def list_presets() -> list[PresetRead]:
    """Industry presets a new business can start from (``preset`` in ``POST /businesses``)."""
    return [
        PresetRead(
            key=preset.key,
            label=preset.label,
            industry=preset.industry,
            description=preset.description,
            custom_field_definitions=preset.custom_fields,
        )
        for preset in PRESETS.values()
    ]


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

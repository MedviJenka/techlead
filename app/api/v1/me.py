from fastapi import APIRouter

from app.api.deps import AccountServiceDep
from app.core.auth import CurrentUser
from app.schemas.account import MeRead

router = APIRouter(prefix="/me", tags=["account"])


@router.get("", response_model=MeRead)
async def me(user: CurrentUser, service: AccountServiceDep) -> MeRead:
    return await service.me(user)

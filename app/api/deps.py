from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.repositories import BusinessRepository
from app.services import BusinessService

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_business_service(session: SessionDep) -> BusinessService:
    return BusinessService(session, BusinessRepository(session))


BusinessServiceDep = Annotated[BusinessService, Depends(get_business_service)]

import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models import Business
from app.repositories import BusinessRepository
from app.schemas import BusinessCreate

logger = logging.getLogger(__name__)


class BusinessService:
    def __init__(self, session: AsyncSession, repository: BusinessRepository) -> None:
        self._session = session
        self._repository = repository

    async def create(self, data: BusinessCreate) -> Business:
        if await self._repository.get_by_slug(data.slug) is not None:
            raise ConflictError(f"Business slug '{data.slug}' is already taken")
        try:
            business = await self._repository.add(Business(**data.model_dump(mode="json")))
            await self._session.commit()
        except IntegrityError as exc:  # lost a race with a concurrent create of the same slug
            await self._session.rollback()
            raise ConflictError(f"Business slug '{data.slug}' is already taken") from exc
        logger.info("business_created", extra={"business_id": str(business.id), "slug": business.slug})
        return business

    async def get(self, business_id: uuid.UUID) -> Business:
        business = await self._repository.get(business_id)
        if business is None:
            raise NotFoundError(f"Business {business_id} not found")
        return business

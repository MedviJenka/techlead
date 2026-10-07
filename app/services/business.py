import logging
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models import Business
from app.repositories import BusinessRepository
from app.schemas import BusinessCreate

logger = logging.getLogger(__name__)


def _slug_taken(slug: str) -> ConflictError:
    return ConflictError(f"Business slug '{slug}' is already taken")


async def require_business(repository: BusinessRepository, business_id: uuid.UUID) -> Business:
    """The business, or ``NotFoundError``. Every tenant-scoped service checks this first (unknown tenant -> 404)."""
    business = await repository.get(business_id)
    if business is None:
        raise NotFoundError(f"Business {business_id} not found")
    return business


def _to_model(data: BusinessCreate) -> Business:
    """Explicit field mapping: only these columns are client-settable (no mass assignment)."""
    return Business(
        name=data.name,
        slug=data.slug,
        industry=data.industry,
        timezone=data.timezone,
        configuration=data.configuration,
        custom_field_definitions=data.custom_field_definitions,
        ai_configuration=data.ai_configuration.to_ai_configuration().model_dump(mode="json"),
    )


class BusinessService:
    def __init__(self, session: AsyncSession, repository: BusinessRepository) -> None:
        self._session = session
        self._repository = repository

    async def create(self, data: BusinessCreate) -> Business:
        if await self._repository.get_by_slug(data.slug) is not None:
            raise _slug_taken(data.slug)
        try:
            business = await self._repository.add(_to_model(data))
            await self._session.commit()
        except IntegrityError as exc:  # lost a race with a concurrent create of the same slug
            await self._session.rollback()
            raise _slug_taken(data.slug) from exc
        logger.info("business_created", extra={"business_id": str(business.id), "slug": business.slug})
        return business

    async def get(self, business_id: uuid.UUID) -> Business:
        return await require_business(self._repository, business_id)

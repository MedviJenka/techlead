import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Business


class BusinessRepository:
    """Persistence for tenants. Tenant-owned tables get their own repositories scoped by business_id."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, business_id: uuid.UUID) -> Business | None:
        return await self._session.get(Business, business_id)

    async def get_by_slug(self, slug: str) -> Business | None:
        return await self._session.scalar(select(Business).where(Business.slug == slug))

    async def add(self, business: Business) -> Business:
        self._session.add(business)
        await self._session.flush()
        await self._session.refresh(business)
        return business

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity


class ActivityRepository:
    """Append-only, tenant-scoped activity log (rows are never updated)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_all(self, activities: Sequence[Activity]) -> None:
        self._session.add_all(activities)
        await self._session.flush()

    async def list_for_lead(
        self, business_id: uuid.UUID, lead_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Activity], int]:
        """Chronological page (``created_at ASC, id ASC``) plus the lead's total activity count.

        Callers must have checked that the lead belongs to the business (404 otherwise).
        """
        filters = (Activity.business_id == business_id, Activity.lead_id == lead_id)
        total = await self._session.scalar(select(func.count()).select_from(Activity).where(*filters))
        stmt = select(Activity).where(*filters).order_by(Activity.created_at, Activity.id).limit(limit).offset(offset)
        activities = (await self._session.scalars(stmt)).all()
        return list(activities), total or 0

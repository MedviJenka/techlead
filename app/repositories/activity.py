import uuid

from postgrest import CountMethod
from supabase import AsyncClient

from app.models import Activity


class ActivityRepository:
    """Tenant-scoped activity log. Activities are written only with their lead, by ``LeadRepository.save``."""

    def __init__(self, db: AsyncClient) -> None:
        self._db = db

    async def list_for_lead(
        self, business_id: uuid.UUID, lead_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Activity], int]:
        """Chronological page (``created_at ASC, id ASC``) plus the lead's total activity count.

        Callers must have checked that the lead belongs to the business (404 otherwise).
        """
        response = (
            await self._db.table("activities")
            .select("*", count=CountMethod.exact)
            .eq("business_id", str(business_id))
            .eq("lead_id", str(lead_id))
            .order("created_at")
            .order("id")
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [Activity.model_validate(row) for row in response.data], response.count or 0

    async def recent(self, business_id: uuid.UUID, limit: int) -> list[Activity]:
        """The business's latest activities, newest first (``created_at DESC, id DESC``)."""
        response = (
            await self._db.table("activities")
            .select("*")
            .eq("business_id", str(business_id))
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )
        return [Activity.model_validate(row) for row in response.data]

import uuid
from collections.abc import Collection
from datetime import datetime
from typing import Any, cast

from postgrest import CountMethod
from supabase import AsyncClient

from ai.schemas.enums import ActivityType
from app.models import Activity

# PostgREST caps each response at this many rows (Supabase default).
_MAX_ROWS = 1000


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

    async def latest_of_type(
        self, business_id: uuid.UUID, lead_id: uuid.UUID, activity_type: ActivityType
    ) -> Activity | None:
        response = (
            await self._db.table("activities")
            .select("*")
            .eq("business_id", str(business_id))
            .eq("lead_id", str(lead_id))
            .eq("activity_type", activity_type.value)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        return Activity.model_validate(response.data[0]) if response.data else None

    async def has_message(self, business_id: uuid.UUID, message_id: str) -> bool:
        """Whether a channel message (``metadata.message_id``, e.g. a WhatsApp ``wamid``) is already recorded."""
        response = (
            await self._db.table("activities")
            .select("id")
            .eq("business_id", str(business_id))
            .eq("metadata->>message_id", message_id)
            .limit(1)
            .execute()
        )
        return bool(response.data)

    async def first_of_types(
        self, business_id: uuid.UUID, activity_types: Collection[ActivityType]
    ) -> dict[uuid.UUID, datetime]:
        """When each lead first had an activity of ``activity_types`` (e.g. its first outbound contact)."""
        firsts: dict[uuid.UUID, datetime] = {}
        types = [activity_type.value for activity_type in activity_types]
        fetched = 0
        while True:
            response = (
                await self._db.table("activities")
                .select("lead_id,created_at")
                .eq("business_id", str(business_id))
                .in_("activity_type", types)
                .order("created_at")
                .order("id")
                .range(fetched, fetched + _MAX_ROWS - 1)
                .execute()
            )
            for row in cast(list[dict[str, Any]], response.data):
                lead_id = uuid.UUID(row["lead_id"])
                firsts.setdefault(lead_id, datetime.fromisoformat(row["created_at"]))
            fetched += len(response.data)
            if len(response.data) < _MAX_ROWS:
                return firsts

    async def all_for_lead(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> list[Activity]:
        """Every activity of one lead, chronological."""
        return await self._all(business_id, lead_id=str(lead_id))

    async def all_for_business(self, business_id: uuid.UUID) -> list[Activity]:
        """Every activity of the business, chronological (for rescoring all leads at once)."""
        return await self._all(business_id)

    async def _all(self, business_id: uuid.UUID, **equals: str) -> list[Activity]:
        activities: list[Activity] = []
        while True:
            query = self._db.table("activities").select("*").eq("business_id", str(business_id))
            for column, value in equals.items():
                query = query.eq(column, value)
            response = (
                await query.order("created_at")
                .order("id")
                .range(len(activities), len(activities) + _MAX_ROWS - 1)
                .execute()
            )
            activities += [Activity.model_validate(row) for row in response.data]
            if len(response.data) < _MAX_ROWS:
                return activities

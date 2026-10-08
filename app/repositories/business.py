import uuid
from typing import Any

from supabase import AsyncClient

from app.core.supabase import to_json
from app.models import Business


class BusinessRepository:
    """Persistence for tenants. Tenant-owned tables get their own repositories scoped by business_id."""

    def __init__(self, db: AsyncClient) -> None:
        self._db = db

    async def get(self, business_id: uuid.UUID) -> Business | None:
        response = await self._db.table("businesses").select("*").eq("id", str(business_id)).limit(1).execute()
        return Business.model_validate(response.data[0]) if response.data else None

    async def get_by_slug(self, slug: str) -> Business | None:
        response = await self._db.table("businesses").select("*").eq("slug", slug).limit(1).execute()
        return Business.model_validate(response.data[0]) if response.data else None

    async def add(self, values: dict[str, Any]) -> Business:
        """Insert and return the stored row (with id and timestamps). A taken slug raises ``APIError`` 23505."""
        response = await self._db.table("businesses").insert(to_json(values)).execute()
        return Business.model_validate(response.data[0])

    async def delete(self, business_id: uuid.UUID) -> None:
        """Delete the business and, by cascade, everything it owns."""
        await self._db.table("businesses").delete().eq("id", str(business_id)).execute()

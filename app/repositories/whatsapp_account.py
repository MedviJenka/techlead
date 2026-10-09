import uuid
from datetime import UTC, datetime
from typing import Any

from supabase import AsyncClient

from app.core.supabase import to_json
from app.models import WhatsAppAccount


class WhatsAppAccountRepository:
    """Which business owns which WhatsApp number (one per business)."""

    def __init__(self, db: AsyncClient) -> None:
        self._db = db

    async def get(self, business_id: uuid.UUID) -> WhatsAppAccount | None:
        response = (
            await self._db.table("whatsapp_accounts").select("*").eq("business_id", str(business_id)).limit(1).execute()
        )
        return WhatsAppAccount.model_validate(response.data[0]) if response.data else None

    async def get_by_phone_number_id(self, phone_number_id: str) -> WhatsAppAccount | None:
        """The account an inbound webhook belongs to (``metadata.phone_number_id``)."""
        response = (
            await self._db.table("whatsapp_accounts")
            .select("*")
            .eq("phone_number_id", phone_number_id)
            .limit(1)
            .execute()
        )
        return WhatsAppAccount.model_validate(response.data[0]) if response.data else None

    async def save(self, business_id: uuid.UUID, values: dict[str, Any]) -> WhatsAppAccount:
        """Insert or replace the business's account. A number another business owns raises ``APIError`` 23505."""
        row = to_json(values | {"business_id": business_id, "updated_at": datetime.now(UTC)})
        response = await self._db.table("whatsapp_accounts").upsert(row, on_conflict="business_id").execute()
        return WhatsAppAccount.model_validate(response.data[0])

    async def delete(self, business_id: uuid.UUID) -> None:
        await self._db.table("whatsapp_accounts").delete().eq("business_id", str(business_id)).execute()

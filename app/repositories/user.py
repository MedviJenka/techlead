import uuid
from typing import Any

from supabase import AsyncClient

from app.core.supabase import to_json
from app.models import User


class UserRepository:
    def __init__(self, db: AsyncClient) -> None:
        self._db = db

    async def get(self, user_id: uuid.UUID) -> User | None:
        response = await self._db.table("users").select("*").eq("id", str(user_id)).limit(1).execute()
        return User.model_validate(response.data[0]) if response.data else None

    async def add(self, values: dict[str, Any]) -> User:
        """Insert and return the stored row. A taken id or email raises ``APIError`` 23505."""
        response = await self._db.table("users").insert(to_json(values)).execute()
        return User.model_validate(response.data[0])

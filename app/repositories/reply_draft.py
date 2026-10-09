import uuid
from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any

from postgrest import CountMethod
from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.core.supabase import to_json
from app.models import ReplyDraft, ReplyDraftStatus

_UNIQUE_VIOLATION = "23505"
_MAX_ERROR_LENGTH = 2000


class ReplyDraftRepository:
    """AI-drafted replies awaiting the owner. Tenant-scoped: every query filters ``business_id``.

    State changes are conditional updates (``WHERE status IN ...``), so two decisions on one draft (a double tap,
    or the phone and the dashboard at once) never both win.
    """

    def __init__(self, db: AsyncClient) -> None:
        self._db = db

    async def add(self, values: dict[str, Any]) -> ReplyDraft | None:
        """Insert a draft; None when the lead already has an undecided one (``uq_reply_drafts_open_lead``)."""
        try:
            response = await self._db.table("reply_drafts").insert(to_json(values)).execute()
        except APIError as exc:
            if exc.code == _UNIQUE_VIOLATION:
                return None
            raise
        return ReplyDraft.model_validate(response.data[0])

    async def get(self, business_id: uuid.UUID, draft_id: uuid.UUID) -> ReplyDraft | None:
        response = (
            await self._db.table("reply_drafts")
            .select("*")
            .eq("business_id", str(business_id))
            .eq("id", str(draft_id))
            .limit(1)
            .execute()
        )
        return ReplyDraft.model_validate(response.data[0]) if response.data else None

    async def with_status(
        self, business_id: uuid.UUID, statuses: Collection[ReplyDraftStatus], limit: int
    ) -> list[ReplyDraft]:
        """Newest first."""
        response = (
            await self._db.table("reply_drafts")
            .select("*")
            .eq("business_id", str(business_id))
            .in_("status", [status.value for status in statuses])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [ReplyDraft.model_validate(row) for row in response.data]

    async def count(self, business_id: uuid.UUID, statuses: Collection[ReplyDraftStatus]) -> int:
        response = (
            await self._db.table("reply_drafts")
            .select("id", count=CountMethod.exact)
            .eq("business_id", str(business_id))
            .in_("status", [status.value for status in statuses])
            .limit(1)
            .execute()
        )
        return response.count or 0

    async def for_lead(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> list[ReplyDraft]:
        """The lead's drafts, newest first."""
        response = (
            await self._db.table("reply_drafts")
            .select("*")
            .eq("business_id", str(business_id))
            .eq("lead_id", str(lead_id))
            .order("created_at", desc=True)
            .execute()
        )
        return [ReplyDraft.model_validate(row) for row in response.data]

    async def awaiting_edit(self, business_id: uuid.UUID) -> ReplyDraft | None:
        """The draft whose new text the owner is typing (the latest one they tapped Edit on)."""
        drafts = await self.with_status(business_id, [ReplyDraftStatus.AWAITING_EDIT], 1)
        return drafts[0] if drafts else None

    async def transition(
        self, draft: ReplyDraft, from_statuses: Collection[ReplyDraftStatus], values: dict[str, Any]
    ) -> ReplyDraft | None:
        """Apply ``values`` if the draft is still in one of ``from_statuses``; None when another decision won."""
        if values.get("last_error"):
            values = values | {"last_error": values["last_error"][:_MAX_ERROR_LENGTH]}
        response = (
            await self._db.table("reply_drafts")
            .update(to_json(values | {"updated_at": datetime.now(UTC)}))
            .eq("business_id", str(draft.business_id))
            .eq("id", str(draft.id))
            .in_("status", [status.value for status in from_statuses])
            .execute()
        )
        return ReplyDraft.model_validate(response.data[0]) if response.data else None

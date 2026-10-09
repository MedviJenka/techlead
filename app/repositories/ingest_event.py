import uuid
from datetime import UTC, datetime
from typing import Any, cast

from supabase import AsyncClient

from app.core.supabase import to_json
from app.models import IngestEvent, IngestStatus

_MAX_ERROR_LENGTH = 2000


class IngestEventRepository:
    """Inbound webhook events (MAIN_PLAN §59). Claiming is a database function (db/004_functions.sql)."""

    def __init__(self, db: AsyncClient) -> None:
        self._db = db

    async def claim(
        self,
        business_id: uuid.UUID,
        source: str,
        external_event_id: str,
        event_type: str,
        payload: dict[str, Any],
        stale_seconds: int = 300,
    ) -> IngestEvent | None:
        """The event to process, or None for a duplicate (already processed, or being processed right now)."""
        params = {
            "p_business_id": business_id,
            "p_source": source,
            "p_external_event_id": external_event_id,
            "p_event_type": event_type,
            "p_payload": payload,
            "p_stale_seconds": stale_seconds,
        }
        response = await self._db.rpc("claim_ingest_event", to_json(params)).execute()
        rows = cast(list[dict[str, Any]], response.data or [])
        return IngestEvent.model_validate(rows[0]) if rows else None

    async def finish(self, event: IngestEvent, status: IngestStatus, error: str | None = None) -> None:
        now = datetime.now(UTC)
        values: dict[str, Any] = {
            "status": status,
            "updated_at": now,
            "last_error": error[:_MAX_ERROR_LENGTH] if error else None,
        }
        if status is not IngestStatus.FAILED:
            values["processed_at"] = now
        await self._db.table("ingest_events").update(to_json(values)).eq("id", str(event.id)).execute()

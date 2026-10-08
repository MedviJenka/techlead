import uuid
from datetime import UTC, datetime
from typing import Any, cast

from postgrest import CountMethod
from supabase import AsyncClient

from app.core.supabase import to_json
from app.models import Lead
from app.schemas.lead import LeadListParams, LeadSummary

# List views select only these columns: they never load (or leak) `raw_payload`.
_SUMMARY_COLUMNS = ",".join(LeadSummary.model_fields)
# PostgREST caps each response at this many rows (Supabase default).
_MAX_ROWS = 1000
_SEARCH_COLUMNS = ("first_name", "last_name", "email", "phone", "company_name")


def _search_filter(q: str) -> str:
    """PostgREST ``or`` filter: any search column contains ``q`` (case-insensitive, ``%`` and ``_`` literal)."""
    like = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    # Double-quoted so commas and parentheses in `q` cannot break the filter syntax.
    quoted = '"' + f"*{like}*".replace("\\", "\\\\").replace('"', '\\"') + '"'
    return ",".join(f"{column}.ilike.{quoted}" for column in _SEARCH_COLUMNS)


class LeadRepository:
    """Tenant-scoped lead persistence. Every query filters ``business_id`` (never a lead id alone)."""

    def __init__(self, db: AsyncClient) -> None:
        self._db = db

    async def _first(self, business_id: uuid.UUID, **equals: str) -> Lead | None:
        """The oldest lead of the business matching every ``column=value`` in ``equals``."""
        query = self._db.table("leads").select("*").eq("business_id", str(business_id))
        for column, value in equals.items():
            query = query.eq(column, value)
        response = await query.order("created_at").order("id").limit(1).execute()
        return Lead.model_validate(response.data[0]) if response.data else None

    async def get(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
        return await self._first(business_id, id=str(lead_id))

    async def get_by_external_id(self, business_id: uuid.UUID, source: str, external_id: str) -> Lead | None:
        return await self._first(business_id, source=source, external_id=external_id)

    async def get_oldest_by_email(self, business_id: uuid.UUID, email: str) -> Lead | None:
        return await self._first(business_id, email=email)

    async def get_oldest_by_phone(self, business_id: uuid.UUID, phone: str) -> Lead | None:
        return await self._first(business_id, phone=phone)

    async def save(
        self,
        business_id: uuid.UUID,
        lead_id: uuid.UUID | None,
        values: dict[str, Any],
        activities: list[dict[str, Any]],
    ) -> Lead:
        """Insert (``lead_id=None``) or update a lead, then append ``activities`` to it.

        Two requests, not one transaction: if the activity insert fails, the lead change is kept without its events.
        """
        leads = self._db.table("leads")
        if lead_id is None:
            query = leads.insert(to_json(values | {"business_id": business_id}))
        else:
            changes = to_json(values | {"updated_at": datetime.now(UTC)})
            query = leads.update(changes).eq("business_id", str(business_id)).eq("id", str(lead_id))
        response = await query.execute()
        if not response.data:
            raise LookupError(f"Lead {lead_id} not found")
        lead = Lead.model_validate(response.data[0])
        if activities:
            # A bulk insert needs the same keys in every row.
            rows = [
                {"business_id": business_id, "lead_id": lead.id, "channel": None, "metadata": {}} | a
                for a in activities
            ]
            await self._db.table("activities").insert(to_json(rows)).execute()
        return lead

    async def list_all(self, business_id: uuid.UUID) -> list[LeadSummary]:
        """Every lead of the business (summary columns), fetched in pages of PostgREST's default row limit."""
        return [LeadSummary.model_validate(row) for row in await self._all_rows(business_id, _SUMMARY_COLUMNS)]

    async def list_full(self, business_id: uuid.UUID) -> list[Lead]:
        """Every lead of the business with all columns (for rescoring)."""
        return [Lead.model_validate(row) for row in await self._all_rows(business_id, "*")]

    async def _all_rows(self, business_id: uuid.UUID, columns: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        while True:
            response = (
                await self._db.table("leads")
                .select(columns)
                .eq("business_id", str(business_id))
                .order("id")
                .range(len(rows), len(rows) + _MAX_ROWS - 1)
                .execute()
            )
            rows += cast(list[dict[str, Any]], response.data)
            if len(response.data) < _MAX_ROWS:
                return rows

    async def list_page(self, business_id: uuid.UUID, params: LeadListParams) -> tuple[list[LeadSummary], int]:
        """One page ordered newest first (``created_at DESC, id DESC``) plus the total match count."""
        query = (
            self._db.table("leads")
            .select(_SUMMARY_COLUMNS, count=CountMethod.exact)
            .eq("business_id", str(business_id))
        )
        if params.status is not None:
            query = query.eq("status", params.status)
        if params.priority is not None:
            query = query.eq("priority", params.priority.value)
        if params.source is not None:
            query = query.eq("source", params.source)
        if params.q is not None:
            query = query.or_(_search_filter(params.q))
        response = (
            await query.order("created_at", desc=True)
            .order("id", desc=True)
            .range(params.offset, params.offset + params.limit - 1)
            .execute()
        )
        return [LeadSummary.model_validate(row) for row in response.data], response.count or 0

import uuid

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.models import Lead
from app.schemas.lead import LeadListParams

# ILIKE wildcards and the escape character itself, matched literally in `q` searches.
_LIKE_ESCAPE = "\\"


def _escape_like(value: str) -> str:
    return value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2).replace("%", r"\%").replace("_", r"\_")


def _list_filters(business_id: uuid.UUID, params: LeadListParams) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [Lead.business_id == business_id]
    if params.status is not None:
        filters.append(Lead.status == params.status)
    if params.priority is not None:
        filters.append(Lead.priority == params.priority)
    if params.source is not None:
        filters.append(Lead.source == params.source)
    if params.q is not None:
        pattern = f"%{_escape_like(params.q)}%"
        columns = (Lead.first_name, Lead.last_name, Lead.email, Lead.phone, Lead.company_name)
        filters.append(or_(*(column.ilike(pattern, escape=_LIKE_ESCAPE) for column in columns)))
    return filters


class LeadRepository:
    """Tenant-scoped lead persistence. Every query filters ``business_id`` (never ``session.get`` by id alone)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _scoped(self, business_id: uuid.UUID) -> Select[Lead]:
        return select(Lead).where(Lead.business_id == business_id)

    async def get(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
        return await self._session.scalar(self._scoped(business_id).where(Lead.id == lead_id))

    async def get_by_external_id(self, business_id: uuid.UUID, source: str, external_id: str) -> Lead | None:
        stmt = self._scoped(business_id).where(Lead.source == source, Lead.external_id == external_id)
        return await self._session.scalar(stmt)

    async def get_oldest_by_email(self, business_id: uuid.UUID, email: str) -> Lead | None:
        return await self._oldest(business_id, Lead.email == email)

    async def get_oldest_by_phone(self, business_id: uuid.UUID, phone: str) -> Lead | None:
        return await self._oldest(business_id, Lead.phone == phone)

    async def _oldest(self, business_id: uuid.UUID, condition: ColumnElement[bool]) -> Lead | None:
        stmt = self._scoped(business_id).where(condition).order_by(Lead.created_at, Lead.id).limit(1)
        return await self._session.scalar(stmt)

    async def add(self, lead: Lead) -> None:
        self._session.add(lead)
        # INSERT ... RETURNING loads id/created_at/updated_at/status defaults; no refresh needed.
        await self._session.flush()

    async def flush(self) -> None:
        await self._session.flush()

    async def list_page(self, business_id: uuid.UUID, params: LeadListParams) -> tuple[list[Lead], int]:
        """One page ordered newest first (``created_at DESC, id DESC``) plus the total match count.

        ``raw_payload`` is deferred with ``raiseload``: list views never load (or leak) the source payload.
        """
        filters = _list_filters(business_id, params)
        total = await self._session.scalar(select(func.count()).select_from(Lead).where(*filters))
        stmt = (
            select(Lead)
            .where(*filters)
            .options(defer(Lead.raw_payload, raiseload=True))
            .order_by(Lead.created_at.desc(), Lead.id.desc())
            .limit(params.limit)
            .offset(params.offset)
        )
        leads = (await self._session.scalars(stmt)).all()
        return list(leads), total or 0

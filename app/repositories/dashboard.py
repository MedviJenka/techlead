"""Business-scoped dashboard aggregates, computed in SQL (one query per section, no per-lead loading).

The rule *values* (what counts as hot, closed, stale ...) are business decisions owned by the service layer
(``app/services/lead_rules.py``) and passed in as ``DashboardRules``.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from ai.schemas.enums import ActivityType, Channel, Priority
from app.models import Activity, Lead

UNKNOWN_KEY = "unknown"
# Score buckets in display order; bounds are inclusive and the last key holds unscored leads.
SCORE_BUCKETS: tuple[tuple[str, int, int], ...] = (("0-39", 0, 39), ("40-69", 40, 69), ("70-100", 70, 100))

type DistributionColumn = Literal["source", "status"]


@dataclass(frozen=True)
class DashboardRules:
    hot_priorities: frozenset[Priority]
    closed_statuses: frozenset[str]
    new_status: str
    qualified_status: str
    proposal_status: str
    inactive_status: str
    stale_before: datetime
    priority_rank: Mapping[Priority, int]


@dataclass(frozen=True)
class CountsRow:
    total: int
    new: int
    hot: int
    qualified: int
    waiting_for_proposal: int
    needs_follow_up: int
    inactive: int
    average_score: Decimal | None


@dataclass(frozen=True)
class RecentActivityRow:
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None
    activity_type: ActivityType
    channel: Channel | None
    description: str
    created_at: datetime


def _count_where(condition: ColumnElement[bool]) -> ColumnElement[int]:
    return func.count().filter(condition)


def _lead_name(first_name: str | None, last_name: str | None) -> str | None:
    return " ".join(part for part in (first_name, last_name) if part) or None


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def counts(self, business_id: uuid.UUID, rules: DashboardRules) -> CountsRow:
        open_lead = Lead.status.not_in(rules.closed_statuses)
        stale_contact = or_(Lead.last_contact_at.is_(None), Lead.last_contact_at < rules.stale_before)
        stale_activity = func.coalesce(Lead.last_contact_at, Lead.created_at) < rules.stale_before
        stmt = select(
            func.count(),
            _count_where(Lead.status == rules.new_status),
            _count_where(Lead.priority.in_(rules.hot_priorities)),
            _count_where(Lead.status == rules.qualified_status),
            _count_where(Lead.status == rules.proposal_status),
            _count_where(and_(open_lead, stale_contact)),
            _count_where(or_(Lead.status == rules.inactive_status, and_(open_lead, stale_activity))),
            func.avg(Lead.lead_score),
        ).where(Lead.business_id == business_id)
        row = (await self._session.execute(stmt)).one()
        return CountsRow(*row)

    async def distribution(self, business_id: uuid.UUID, column: DistributionColumn) -> list[tuple[str, int]]:
        """Present keys only, ``count DESC`` then ``key ASC``; null values are reported as ``"unknown"``."""
        key = func.coalesce(getattr(Lead, column), UNKNOWN_KEY).label("key")
        count = func.count().label("count")
        stmt = select(key, count).where(Lead.business_id == business_id).group_by(key).order_by(count.desc(), key.asc())
        rows = (await self._session.execute(stmt)).tuples().all()
        return [(str(bucket), int(total)) for bucket, total in rows]

    async def score_distribution(self, business_id: uuid.UUID) -> dict[str, int]:
        """Always every bucket of ``SCORE_BUCKETS`` plus ``"unknown"``, in display order, zeros included."""
        columns = [_count_where(Lead.lead_score.between(low, high)) for _, low, high in SCORE_BUCKETS]
        columns.append(_count_where(Lead.lead_score.is_(None)))
        row = (await self._session.execute(select(*columns).where(Lead.business_id == business_id))).one()
        keys = [label for label, _, _ in SCORE_BUCKETS] + [UNKNOWN_KEY]
        return dict(zip(keys, (int(value) for value in row), strict=True))

    async def recent_activities(self, business_id: uuid.UUID, limit: int = 10) -> list[RecentActivityRow]:
        stmt = (
            select(Activity, Lead.first_name, Lead.last_name)
            .join(Lead, and_(Lead.business_id == Activity.business_id, Lead.id == Activity.lead_id))
            .where(Activity.business_id == business_id)
            .order_by(Activity.created_at.desc(), Activity.id.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).tuples().all()
        return [
            RecentActivityRow(
                id=activity.id,
                lead_id=activity.lead_id,
                lead_name=_lead_name(first_name, last_name),
                activity_type=activity.activity_type,
                channel=activity.channel,
                description=activity.description,
                created_at=activity.created_at,
            )
            for activity, first_name, last_name in rows
        ]

    async def top_leads(self, business_id: uuid.UUID, rules: DashboardRules, limit: int = 5) -> list[Lead]:
        """Open leads by priority rank, then score (nulls last), then newest first."""
        rank = case(dict(rules.priority_rank), value=Lead.priority, else_=0)
        stmt = (
            select(Lead)
            .where(Lead.business_id == business_id, Lead.status.not_in(rules.closed_statuses))
            .options(defer(Lead.raw_payload, raiseload=True))
            .order_by(rank.desc(), Lead.lead_score.desc().nulls_last(), Lead.created_at.desc(), Lead.id.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

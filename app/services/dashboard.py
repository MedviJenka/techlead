import asyncio
import statistics
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from supabase import AsyncClient

from ai.schemas.enums import Priority
from app.intelligence import next_follow_up
from app.intelligence.facts import OUTBOUND_TYPES
from app.models import Activity
from app.models.reply_draft import OPEN_DRAFT_STATUSES
from app.repositories import ActivityRepository, BusinessRepository, LeadRepository, ReplyDraftRepository
from app.schemas.configuration import BusinessConfiguration
from app.schemas.dashboard import Bucket, DashboardCounts, DashboardSummary, RecentActivity, ResponseMetrics
from app.schemas.lead import LeadSummary
from app.services.business import BusinessSettings, require_business

HOT_PRIORITIES = frozenset({Priority.HIGH, Priority.CRITICAL})
PRIORITY_RANK: dict[Priority | None, int] = {
    None: 0,
    Priority.LOW: 1,
    Priority.MEDIUM: 2,
    Priority.HIGH: 3,
    Priority.CRITICAL: 4,
}
STALE_AFTER = timedelta(days=7)
RECENT_ACTIVITY_LIMIT = 10
TOP_LEADS_LIMIT = 5
SCORE_BUCKETS = ("0-39", "40-69", "70-100", "unknown")


def _score_bucket(score: int | None) -> str:
    if score is None:
        return "unknown"
    return "0-39" if score < 40 else "40-69" if score < 70 else "70-100"


def _buckets(keys: Iterable[str]) -> list[Bucket]:
    """Largest first, ties by key."""
    counts = Counter(keys)
    return [Bucket(key=key, count=count) for key, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _top_rank(lead: LeadSummary) -> tuple[int, int, datetime, uuid.UUID]:
    """Priority, then score (unscored last), then newest."""
    score = -1 if lead.lead_score is None else lead.lead_score
    return PRIORITY_RANK[lead.priority], score, lead.created_at, lead.id


def _overdue(config: BusinessConfiguration, lead: LeadSummary, now: datetime) -> bool:
    follow_up = next_follow_up(config, lead, now)
    return follow_up is not None and follow_up.overdue


def response_metrics(
    leads: list[LeadSummary],
    first_responses: Mapping[uuid.UUID, datetime],
    closed: frozenset[str],
    pending_approvals: int,
) -> ResponseMetrics:
    """``first_responses``: when each lead got its first outbound message or call."""
    delays = [
        (first_responses[lead.id] - lead.created_at).total_seconds()
        for lead in leads
        if lead.id in first_responses and first_responses[lead.id] >= lead.created_at
    ]
    return ResponseMetrics(
        median_first_response_seconds=statistics.median(delays) if delays else None,
        responded=sum(lead.id in first_responses for lead in leads),
        without_response=sum(lead.id not in first_responses and lead.status not in closed for lead in leads),
        pending_approvals=pending_approvals,
    )


def summarize(
    leads: list[LeadSummary],
    activities: list[Activity],
    now: datetime,
    config: BusinessConfiguration | None = None,
    first_responses: Mapping[uuid.UUID, datetime] | None = None,
    pending_approvals: int = 0,
) -> DashboardSummary:
    """Dashboard from all of a business's leads and its latest activities, under the business's configuration."""
    config = config or BusinessConfiguration()
    closed = frozenset(config.closed_statuses)
    stale_before = now - STALE_AFTER
    open_leads = [lead for lead in leads if lead.status not in closed]
    scores = [lead.lead_score for lead in leads if lead.lead_score is not None]
    counts = DashboardCounts(
        total=len(leads),
        new=sum(lead.status == "new" for lead in leads),
        hot=sum(lead.priority in HOT_PRIORITIES for lead in leads),
        qualified=sum(lead.status == "qualified" for lead in leads),
        waiting_for_proposal=sum(lead.status == "proposal_sent" for lead in leads),
        needs_follow_up=sum(_overdue(config, lead, now) for lead in open_leads),
        inactive=sum(
            lead.status == "unresponsive"
            or (lead.status not in closed and (lead.last_contact_at or lead.created_at) < stale_before)
            for lead in leads
        ),
        average_score=sum(scores) / len(scores) if scores else None,
    )
    score_counts = Counter(_score_bucket(lead.lead_score) for lead in leads)
    names = {lead.id: " ".join(filter(None, (lead.first_name, lead.last_name))) or None for lead in leads}
    return DashboardSummary(
        counts=counts,
        responses=response_metrics(leads, first_responses or {}, closed, pending_approvals),
        by_source=_buckets(lead.source for lead in leads),
        by_status=_buckets(lead.status for lead in leads),
        by_score=[Bucket(key=key, count=score_counts[key]) for key in SCORE_BUCKETS],
        recent_activity=[
            RecentActivity.model_validate(activity.model_dump() | {"lead_name": names.get(activity.lead_id)})
            for activity in activities
        ],
        top_leads=sorted(open_leads, key=_top_rank, reverse=True)[:TOP_LEADS_LIMIT],
        generated_at=now,
    )


class DashboardService:
    def __init__(self, db: AsyncClient) -> None:
        self.businesses = BusinessRepository(db)
        self.leads = LeadRepository(db)
        self.activities = ActivityRepository(db)
        self.drafts = ReplyDraftRepository(db)

    async def summary(self, business_id: uuid.UUID, now: datetime) -> DashboardSummary:
        settings = BusinessSettings.of(await require_business(self.businesses, business_id))
        leads, activities, first_responses, pending = await asyncio.gather(
            self.leads.list_all(business_id),
            self.activities.recent(business_id, RECENT_ACTIVITY_LIMIT),
            self.activities.first_of_types(business_id, OUTBOUND_TYPES),
            self.drafts.count(business_id, OPEN_DRAFT_STATUSES),
        )
        return summarize(leads, activities, now, settings.configuration, first_responses, pending)

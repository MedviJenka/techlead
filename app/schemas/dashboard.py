import uuid
from datetime import datetime

from pydantic import BaseModel

from ai.schemas.enums import ActivityType, Channel
from app.schemas.lead import LeadSummary


class DashboardCounts(BaseModel):
    """Overview cards. They overlap (a lead can be both hot and new); they are not a partition of ``total``."""

    total: int
    new: int
    hot: int
    qualified: int
    needs_follow_up: int
    waiting_for_proposal: int
    inactive: int
    average_score: float | None


class Bucket(BaseModel):
    key: str
    count: int


class RecentActivity(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None
    activity_type: ActivityType
    channel: Channel | None
    description: str
    created_at: datetime


class DashboardSummary(BaseModel):
    counts: DashboardCounts
    by_source: list[Bucket]
    by_status: list[Bucket]
    by_score: list[Bucket]
    recent_activity: list[RecentActivity]
    top_leads: list[LeadSummary]
    generated_at: datetime

from datetime import datetime

from pydantic import BaseModel, Field

from ai.schemas.enums import NextAction, Priority


class NextActionRecommendation(BaseModel):
    """Recommendation only — the application decides whether and how to execute it (MAIN_PLAN §22)."""

    action: NextAction
    priority: Priority
    reason: str = Field(description="Why this action, what changed, and why now")
    due_at: datetime | None = Field(default=None, description="When the action should happen (ISO-8601, timezone-aware)")
    requires_human_approval: bool
    talking_points: list[str] = Field(default_factory=list, description="What the salesperson should cover")

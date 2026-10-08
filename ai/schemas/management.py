from enum import StrEnum

from pydantic import BaseModel, Field

from ai.schemas.enums import NextAction, Priority


class LeadSortField(StrEnum):
    SCORE = "score"
    CREATED_AT = "created_at"
    LAST_CONTACT_AT = "last_contact_at"
    BUDGET = "budget"


class LeadSearchFilter(BaseModel):
    """Validated search intent. The application turns this into a tenant-scoped query — never raw SQL."""

    statuses: list[str] = Field(default_factory=list)
    priorities: list[Priority] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    min_score: int | None = Field(default=None, ge=0, le=100)
    max_score: int | None = Field(default=None, ge=0, le=100)
    min_budget: float | None = Field(default=None, ge=0)
    max_budget: float | None = Field(default=None, ge=0)
    budget_known: bool | None = None
    not_contacted_for_days: int | None = Field(default=None, ge=0, description="No contact in at least N days (or never)")
    text: str | None = Field(default=None, description="Free text matched against name, company and notes")
    sort_by: LeadSortField = LeadSortField.SCORE
    descending: bool = True
    limit: int = Field(default=20, ge=1, le=50)


class LeadHighlight(BaseModel):
    lead_id: str
    name: str
    reason: str
    suggested_action: NextAction


class SalesAssistantAnswer(BaseModel):
    answer: str = Field(description="Direct answer to the user's question")
    highlighted_leads: list[LeadHighlight] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list, description="Data gaps or assumptions")


class PipelineMetrics(BaseModel):
    """Aggregates computed deterministically by the application."""

    total_leads: int
    by_status: dict[str, int]
    by_source: dict[str, int]
    average_score: float | None
    hot_leads_not_contacted: int
    stale_leads: int = Field(description="Active leads without contact for the stale threshold")
    unanswered_proposals: int


class AttentionItem(BaseModel):
    lead_id: str
    name: str
    issue: str
    recommended_action: NextAction
    urgency: Priority


class PipelineReview(BaseModel):
    headline: str = Field(description="One-line summary of the pipeline today")
    attention_items: list[AttentionItem] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    priorities_today: list[str] = Field(default_factory=list, description="Ordered list of what to do first")

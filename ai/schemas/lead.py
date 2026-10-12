from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ai.schemas.enums import ActivityType, Channel

# Fields produced by previous AI runs. Hidden from prompts so agents do not anchor on stale opinions.
_PRIOR_AI_FIELDS: frozenset[str] = frozenset({"lead_score", "sentiment", "ai_summary", "recommended_action"})


class LeadSnapshot(BaseModel):
    """Normalized, read-only view of a lead handed to agents (MAIN_PLAN §5)."""

    id: str
    business_id: str
    external_id: str | None = None
    source: str
    status: str
    priority: str | None = None

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    preferred_channel: Channel | None = None

    company_name: str | None = None
    company_industry: str | None = None
    company_size: str | None = None

    product_interest: str | None = None
    budget: float | None = None
    currency: str | None = None
    timeframe: str | None = None
    notes: str | None = None

    contact_attempts: int = 0
    replied: bool = False

    lead_score: int | None = None
    sentiment: str | None = None
    ai_summary: str | None = None
    recommended_action: str | None = None

    custom_fields: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime
    last_contact_at: datetime | None = None

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or "Unknown"

    def to_prompt_json(self) -> str:
        return self.model_dump_json(indent=2, exclude=set(_PRIOR_AI_FIELDS), exclude_none=True)


class ActivitySnapshot(BaseModel):
    id: str
    business_id: str
    lead_id: str
    activity_type: ActivityType
    channel: Channel | None = None
    description: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class InboundMessage(BaseModel):
    """A new customer message to analyze (WhatsApp, email, chat, transcript...)."""

    channel: Channel
    body: str = Field(min_length=1)
    received_at: datetime
    sender: str | None = None


def render_activities(activities: list[ActivitySnapshot], limit: int = 20) -> str:
    """Most recent activities, oldest first, as compact prompt lines."""
    if not activities:
        return "No recorded activity."
    recent = sorted(activities, key=lambda a: a.created_at)[-limit:]
    return "\n".join(
        f"- {a.created_at.isoformat()} [{a.activity_type.value}"
        f"{'/' + a.channel.value if a.channel else ''}] {a.description}"
        for a in recent
    )


INBOUND_MESSAGE_TYPES: frozenset[ActivityType] = frozenset(
    {ActivityType.WHATSAPP_RECEIVED, ActivityType.EMAIL_RECEIVED}
)


def latest_lead_message(lead: LeadSnapshot, activities: list[ActivitySnapshot]) -> str | None:
    """The text the lead wrote most recently (an inbound message, else the lead's notes): what a reply answers."""
    inbound = sorted((a for a in activities if a.activity_type in INBOUND_MESSAGE_TYPES), key=lambda a: a.created_at)
    for activity in reversed(inbound):
        body = activity.metadata.get("body")
        if isinstance(body, str) and body.strip():
            return body.strip()
    return lead.notes.strip() if lead.notes and lead.notes.strip() else None

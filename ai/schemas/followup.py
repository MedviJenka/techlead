from pydantic import BaseModel, Field

from ai.schemas.enums import Channel


class FollowupDraft(BaseModel):
    """A draft only. Sending is an application action gated by approval (MAIN_PLAN §23)."""

    channel: Channel
    subject: str | None = Field(default=None, description="Email subject; null for other channels")
    message: str = Field(min_length=1)
    objective: str = Field(description="What this message is trying to achieve")
    tone: str
    requires_human_approval: bool = True

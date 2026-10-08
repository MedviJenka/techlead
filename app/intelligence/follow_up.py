"""When a lead's next contact is due (configured per priority and status). Computed on read, never stored."""

from datetime import datetime, timedelta
from typing import Literal, Protocol

from pydantic import BaseModel

from ai.schemas.enums import Priority
from app.schemas.configuration import BusinessConfiguration

FollowUpReason = Literal["first_response", "status", "interval"]


class FollowUpTarget(Protocol):
    @property
    def status(self) -> str: ...
    @property
    def priority(self) -> Priority | None: ...
    @property
    def created_at(self) -> datetime: ...
    @property
    def last_contact_at(self) -> datetime | None: ...


class FollowUp(BaseModel):
    due_at: datetime
    overdue: bool
    reason: FollowUpReason


def next_follow_up(config: BusinessConfiguration, lead: FollowUpTarget, now: datetime) -> FollowUp | None:
    """None for closed leads. Never contacted: first-response window from creation; otherwise from last contact."""
    if lead.status in config.closed_statuses:
        return None
    rules = config.follow_up
    priority = lead.priority or Priority.MEDIUM
    reason: FollowUpReason
    if lead.last_contact_at is None:
        due_at, reason = lead.created_at + timedelta(hours=rules.first_response_hours[priority]), "first_response"
    elif lead.status in rules.status_interval_hours:
        due_at, reason = lead.last_contact_at + timedelta(hours=rules.status_interval_hours[lead.status]), "status"
    else:
        due_at, reason = lead.last_contact_at + timedelta(hours=rules.interval_hours[priority]), "interval"
    return FollowUp(due_at=due_at, overdue=due_at <= now, reason=reason)

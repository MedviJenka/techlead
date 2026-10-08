"""Lead facts: the flat, named values scoring rules test (`app.schemas.configuration.FACT_NAMES`).

Built from the lead row and its activity history only, so the same lead always yields the same facts at a given
``now``. Budget and timeframe come from the conventional ``custom_fields`` keys ``budget`` and ``timeframe``.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ai.schemas.enums import ActivityType
from app.models import Lead

OUTBOUND_TYPES = frozenset({ActivityType.EMAIL_SENT, ActivityType.WHATSAPP_SENT, ActivityType.PHONE_CALL})
INBOUND_TYPES = frozenset({ActivityType.EMAIL_RECEIVED, ActivityType.WHATSAPP_RECEIVED})
PROPOSAL_STATUSES = frozenset({"proposal_sent", "proposal_requested"})

_DAYS_PER_UNIT = {"day": 1, "week": 7, "month": 30, "quarter": 91, "year": 365}
_RELATIVE_DAYS = {
    "immediately": 0,
    "immediate": 0,
    "asap": 0,
    "now": 0,
    "today": 0,
    "this week": 7,
    "next week": 14,
    "this month": 30,
    "next month": 60,
    "this quarter": 91,
    "next quarter": 182,
    "this year": 365,
}
# "2 weeks", "1-3 months", "within 30 days": a range counts as its upper bound (the latest the purchase may be).
_DURATION = re.compile(r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?\+?\s*(day|week|month|quarter|year)s?\b")


@dataclass(frozen=True)
class Event:
    """What facts need from an activity (stored, or about to be written with a new lead)."""

    activity_type: ActivityType
    created_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)


def parse_timeframe_days(value: object) -> int | None:
    """Days until the planned purchase from free text (``"1-3 months"`` -> 90), or None when unknown."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text in _RELATIVE_DAYS:
        return _RELATIVE_DAYS[text]
    match = _DURATION.search(text)
    if match is None:
        return None
    amount = match.group(2) or match.group(1)
    return round(float(amount) * _DAYS_PER_UNIT[match.group(3)])


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _imported(events: Iterable[Event]) -> tuple[int, bool]:
    """(contact attempts, replied) recorded by an import on the lead's creation activity."""
    for event in events:
        if event.activity_type is ActivityType.LEAD_CREATED and event.metadata.get("imported"):
            attempts = event.metadata.get("contact_attempts")
            replied = event.metadata.get("replied")
            return (attempts if isinstance(attempts, int) and attempts >= 0 else 0), replied is True
    return 0, False


def _days(since: datetime | None, now: datetime) -> float | None:
    return None if since is None else max((now - since).total_seconds() / 86_400, 0.0)


def lead_facts(lead: Lead, events: Iterable[Event], now: datetime) -> dict[str, Any]:
    events = sorted(events, key=lambda event: event.created_at)
    imported_attempts, imported_replied = _imported(events)
    outbound = [event for event in events if event.activity_type in OUTBOUND_TYPES]
    inbound = [event for event in events if event.activity_type in INBOUND_TYPES]
    if inbound:
        last_reply = inbound[-1].created_at
        ignored = sum(event.created_at > last_reply for event in outbound)
    else:
        # Without a recorded reply, every attempt (imported ones too, unless the source says it was answered).
        ignored = len(outbound) + (0 if imported_replied else imported_attempts)
    types = {event.activity_type for event in events}
    budget = _number(lead.custom_fields.get("budget"))
    return {
        "status": lead.status,
        "source": lead.source,
        "sentiment": lead.sentiment.value if lead.sentiment else None,
        "has_email": lead.email is not None,
        "has_phone": lead.phone is not None,
        "has_company": lead.company_name is not None,
        "notes": lead.notes,
        "budget": budget,
        "budget_known": budget is not None and budget > 0,
        "timeframe_days": parse_timeframe_days(lead.custom_fields.get("timeframe")),
        "replied": bool(inbound) or imported_replied,
        "contact_attempts": imported_attempts + len(outbound),
        "ignored_follow_ups": ignored,
        "days_since_created": _days(lead.created_at, now),
        "days_since_last_contact": _days(lead.last_contact_at, now),
        "proposal_sent": lead.status in PROPOSAL_STATUSES or ActivityType.PROPOSAL_SENT in types,
        "meeting_scheduled": ActivityType.MEETING_SCHEDULED in types,
    }


def upstream_ai_score(lead: Lead) -> int | None:
    """AI score delivered by the lead's source (``raw_payload.ai.lead_score``), until our own AI scores leads."""
    ai = lead.raw_payload.get("ai")
    score = ai.get("lead_score") if isinstance(ai, dict) else None
    return score if isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 100 else None

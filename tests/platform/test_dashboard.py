"""Dashboard aggregation (`summarize`): pure Python, no database needed."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ai.schemas.enums import ActivityType, Channel, Priority
from app.models import Activity
from app.schemas import Bucket, LeadSummary
from app.schemas.configuration import BusinessConfiguration
from app.services.dashboard import STALE_AFTER, summarize

T0 = datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
NOW = T0 + STALE_AFTER - timedelta(hours=12)  # leads contacted after T0 - 12h are not stale


def _at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def _lead(minutes: int, **fields: Any) -> LeadSummary:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "external_id": None,
        "source": "website",
        "status": "new",
        "priority": None,
        "first_name": None,
        "last_name": None,
        "email": None,
        "phone": None,
        "company_name": None,
        "lead_score": None,
        "sentiment": None,
        "recommended_action": None,
        "last_contact_at": None,
        "created_at": _at(minutes),
        "updated_at": _at(minutes),
    }
    return LeadSummary.model_validate(defaults | fields)


def _activity(lead: LeadSummary, minutes: int, **fields: Any) -> Activity:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "business_id": uuid.uuid4(),
        "lead_id": lead.id,
        "activity_type": ActivityType.LEAD_CREATED,
        "channel": None,
        "description": "test activity",
        "metadata": {},
        "created_at": _at(minutes),
    }
    return Activity.model_validate(defaults | fields)


def _buckets(buckets: list[Bucket]) -> list[tuple[str, int]]:
    return [(bucket.key, bucket.count) for bucket in buckets]


def test_aggregates() -> None:
    stale = T0 - timedelta(days=1)
    leads = [
        _lead(0, status="new", priority=Priority.HIGH, lead_score=90),
        _lead(1, status="qualified", priority=Priority.CRITICAL, lead_score=40, last_contact_at=_at(5)),
        _lead(2, status="won", priority=Priority.CRITICAL, lead_score=99, last_contact_at=stale),
        _lead(3, status="unresponsive", source="email", lead_score=10, last_contact_at=_at(5)),
        _lead(4, status="proposal_sent", priority=Priority.LOW, last_contact_at=_at(5)),
    ]

    summary = summarize(leads, [], NOW)

    counts = summary.counts
    assert [counts.total, counts.new, counts.hot, counts.qualified, counts.waiting_for_proposal] == [5, 1, 3, 1, 1]
    # Every open lead is past its default follow-up window by NOW; inactive adds the unresponsive one.
    assert (counts.needs_follow_up, counts.inactive) == (4, 1)
    assert counts.average_score == 59.75
    assert _buckets(summary.by_source) == [("website", 4), ("email", 1)]
    assert _buckets(summary.by_status) == [
        ("new", 1),
        ("proposal_sent", 1),
        ("qualified", 1),
        ("unresponsive", 1),
        ("won", 1),
    ]
    assert _buckets(summary.by_score) == [("0-39", 1), ("40-69", 1), ("70-100", 2), ("unknown", 1)]
    assert [(lead.status, lead.lead_score) for lead in summary.top_leads] == [
        ("qualified", 40),
        ("new", 90),
        ("proposal_sent", None),
        ("unresponsive", 10),
    ]
    assert summary.generated_at == NOW


def test_empty_business() -> None:
    summary = summarize([], [], NOW)

    assert (summary.counts.total, summary.counts.needs_follow_up, summary.counts.average_score) == (0, 0, None)
    assert summary.by_status == []
    assert _buckets(summary.by_score) == [("0-39", 0), ("40-69", 0), ("70-100", 0), ("unknown", 0)]
    assert summary.recent_activity == []
    assert summary.top_leads == []


def test_top_leads_rank_unscored_last_and_cap_at_five() -> None:
    leads = [_lead(i, priority=Priority.MEDIUM, lead_score=i * 10) for i in range(6)]
    unscored = _lead(9, priority=Priority.MEDIUM)

    top = summarize([*leads, unscored], [], NOW).top_leads

    assert [lead.lead_score for lead in top] == [50, 40, 30, 20, 10]


def test_recent_activity_keeps_order_and_adds_lead_name() -> None:
    named, anonymous = _lead(0, first_name="Omer", last_name="Tal"), _lead(0)
    latest = _activity(anonymous, 2, activity_type=ActivityType.PHONE_CALL, channel=Channel.PHONE)

    rows = summarize([named, anonymous], [latest, _activity(named, 1)], NOW).recent_activity

    assert [row.lead_name for row in rows] == [None, "Omer Tal"]
    assert (rows[0].id, rows[0].channel) == (latest.id, Channel.PHONE)


def test_follow_up_and_closed_statuses_follow_the_configuration() -> None:
    contacted = _lead(0, status="contacted", priority=Priority.LOW, last_contact_at=NOW - timedelta(hours=100))
    done = _lead(1, status="archived", last_contact_at=NOW - timedelta(days=30))
    config = BusinessConfiguration(closed_statuses=["archived"])

    # Low priority: due 168 hours after the last contact by default; "archived" is closed, so never due.
    assert summarize([contacted, done], [], NOW, config).counts.needs_follow_up == 0

    config.follow_up.interval_hours[Priority.LOW] = 72
    assert summarize([contacted, done], [], NOW, config).counts.needs_follow_up == 1


def test_response_metrics_time_to_first_response_and_unanswered_leads() -> None:
    answered_fast = _lead(0)
    answered_slow = _lead(0)
    unanswered = _lead(30)
    closed = _lead(30, status="lost")
    first_responses = {answered_fast.id: _at(1), answered_slow.id: _at(10)}

    summary = summarize(
        [answered_fast, answered_slow, unanswered, closed], [], NOW, first_responses=first_responses,
        pending_approvals=2,
    )

    # Median of 60s and 600s; the closed lead never counts as waiting.
    assert summary.responses.model_dump() == {
        "median_first_response_seconds": 330.0,
        "responded": 2,
        "without_response": 1,
        "pending_approvals": 2,
    }


def test_response_metrics_without_any_response() -> None:
    summary = summarize([_lead(0)], [], NOW)
    assert (summary.responses.median_first_response_seconds, summary.responses.without_response) == (None, 1)

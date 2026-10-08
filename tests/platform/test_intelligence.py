"""Deterministic intelligence (`app.intelligence`) and its configuration schema: pure Python, no database needed."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from ai.schemas.enums import ActivityType, Priority
from app.intelligence import (
    Event,
    custom_field_errors,
    lead_facts,
    next_follow_up,
    parse_timeframe_days,
    priority_for,
    score_lead,
    upstream_ai_score,
)
from app.intelligence.scoring import holds
from app.models import Lead
from app.schemas.configuration import (
    BusinessConfiguration,
    BusinessSettingsUpdate,
    Condition,
    CustomFieldDefinition,
    PriorityThresholds,
    ScoringConfig,
    ScoringRule,
    stored_definitions,
)

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def _lead(**fields: Any) -> Lead:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "business_id": uuid.uuid4(),
        "external_id": None,
        "source": "website",
        "status": "new",
        "priority": None,
        "first_name": None,
        "last_name": None,
        "email": None,
        "phone": None,
        "company_name": None,
        "notes": None,
        "lead_score": None,
        "sentiment": None,
        "ai_summary": None,
        "recommended_action": None,
        "custom_fields": {},
        "raw_payload": {},
        "last_contact_at": None,
        "created_at": NOW - timedelta(days=1),
        "updated_at": NOW - timedelta(days=1),
    }
    return Lead.model_validate(defaults | fields)


def _event(activity_type: ActivityType, hours_ago: float, **metadata: Any) -> Event:
    return Event(activity_type, NOW - timedelta(hours=hours_ago), metadata)


def _rule(rule_id: str, points: int, *conditions: dict[str, Any]) -> ScoringRule:
    return ScoringRule.model_validate({"id": rule_id, "label": rule_id, "points": points, "when": list(conditions)})


# --- facts ---


@pytest.mark.parametrize(
    ("text", "days"),
    [
        ("immediate", 0),
        ("ASAP", 0),
        ("this quarter", 91),
        ("30 days", 30),
        ("within 2 weeks", 14),
        ("1-3 months", 90),
        ("6+ months", 180),
        ("1.5 years", 548),
        ("unknown", None),
        ("", None),
        (None, None),
        (12, None),
    ],
)
def test_parse_timeframe_days(text: object, days: int | None) -> None:
    assert parse_timeframe_days(text) == days


def test_facts_from_the_lead_row() -> None:
    lead = _lead(
        email="a@b.co",
        company_name="Acme",
        notes="Asked about Pricing",
        custom_fields={"budget": 5000, "timeframe": "2 weeks"},
        last_contact_at=NOW - timedelta(days=3),
    )

    facts = lead_facts(lead, [], NOW)

    assert (facts["has_email"], facts["has_phone"], facts["has_company"]) == (True, False, True)
    assert (facts["budget"], facts["budget_known"], facts["timeframe_days"]) == (5000, True, 14)
    assert (facts["days_since_created"], facts["days_since_last_contact"]) == (1, 3)
    assert (facts["replied"], facts["contact_attempts"], facts["ignored_follow_ups"]) == (False, 0, 0)


@pytest.mark.parametrize("budget", [0, -5, "5000", True, None])
def test_budget_must_be_a_positive_number(budget: object) -> None:
    assert lead_facts(_lead(custom_fields={"budget": budget}), [], NOW)["budget_known"] is False


def test_ignored_follow_ups_count_outbound_after_the_last_reply() -> None:
    events = [
        _event(ActivityType.EMAIL_SENT, 50),
        _event(ActivityType.EMAIL_RECEIVED, 40),
        _event(ActivityType.WHATSAPP_SENT, 30),
        _event(ActivityType.PHONE_CALL, 20),
    ]

    facts = lead_facts(_lead(), events, NOW)

    assert (facts["replied"], facts["contact_attempts"], facts["ignored_follow_ups"]) == (True, 3, 2)


def test_imported_history_counts_until_a_reply_is_recorded() -> None:
    imported = _event(ActivityType.LEAD_CREATED, 100, imported=True, contact_attempts=4, replied=False)
    facts = lead_facts(_lead(), [imported, _event(ActivityType.EMAIL_SENT, 10)], NOW)
    assert (facts["contact_attempts"], facts["ignored_follow_ups"], facts["replied"]) == (5, 5, False)

    answered = _event(ActivityType.LEAD_CREATED, 100, imported=True, contact_attempts=4, replied=True)
    facts = lead_facts(_lead(), [answered, _event(ActivityType.EMAIL_SENT, 10)], NOW)
    assert (facts["contact_attempts"], facts["ignored_follow_ups"], facts["replied"]) == (5, 1, True)


def test_proposal_and_meeting_facts() -> None:
    assert lead_facts(_lead(status="proposal_sent"), [], NOW)["proposal_sent"] is True
    events = [_event(ActivityType.PROPOSAL_SENT, 5), _event(ActivityType.MEETING_SCHEDULED, 4)]
    facts = lead_facts(_lead(status="qualified"), events, NOW)
    assert (facts["proposal_sent"], facts["meeting_scheduled"]) == (True, True)


@pytest.mark.parametrize(
    ("raw_payload", "score"),
    [({"ai": {"lead_score": 85}}, 85), ({"ai": {"lead_score": 101}}, None), ({"ai": None}, None), ({}, None)],
)
def test_upstream_ai_score(raw_payload: dict[str, Any], score: int | None) -> None:
    assert upstream_ai_score(_lead(raw_payload=raw_payload)) == score


# --- conditions and scoring ---


@pytest.mark.parametrize(
    ("op", "value", "actual", "expected"),
    [
        ("eq", "Website", "website", True),
        ("eq", True, 1, False),
        ("ne", "lost", None, True),
        ("in", ["a", "b"], "B", True),
        ("contains", "pricing", "Requested PRICING info", True),
        ("contains", "x", ["y", "x"], True),
        ("gt", 7, 7.5, True),
        ("lte", 30, 30, True),
        ("lt", 30, None, False),
        ("gte", 1, True, False),
        ("exists", None, "", False),
        ("missing", None, None, True),
    ],
)
def test_condition_operators(op: str, value: Any, actual: Any, expected: bool) -> None:
    fact = "notes" if op == "contains" else "status"
    assert holds(Condition.model_validate({"fact": fact, "op": op, "value": value}), actual) is expected


def test_score_adds_matched_rule_points_to_the_base() -> None:
    config = ScoringConfig(
        base_score=50,
        rules=[
            _rule("replied", 20, {"fact": "replied", "op": "eq", "value": True}),
            _rule("silent", -30, {"fact": "replied", "op": "eq", "value": False}),
            _rule(
                "mortgage_in_tel_aviv",
                15,
                {"fact": "custom_fields.mortgage_approved", "op": "eq", "value": True},
                {"fact": "custom_fields.city", "op": "eq", "value": "tel aviv"},
            ),
        ],
    )
    custom_fields = {"mortgage_approved": True, "city": "Tel Aviv"}

    breakdown = score_lead(config, {"replied": True}, custom_fields)

    assert [rule.id for rule in breakdown.matched] == ["replied", "mortgage_in_tel_aviv"]
    assert (breakdown.deterministic, breakdown.ai, breakdown.final) == (85, None, 85)


def test_score_is_clamped_and_blended_with_the_ai_score() -> None:
    config = ScoringConfig(
        base_score=90, ai_weight=0.4, rules=[_rule("big", 50, {"fact": "has_email", "op": "exists"})]
    )

    breakdown = score_lead(config, {"has_email": True}, {}, ai_score=91)

    # MAIN_PLAN §48: 100 * 0.6 + 91 * 0.4 = 96.4
    assert (breakdown.deterministic, breakdown.ai, breakdown.final) == (100, 91, 96)


def test_default_rules_follow_main_plan_example() -> None:
    facts = {"budget_known": True, "timeframe_days": 14, "replied": True, "proposal_sent": True}

    breakdown = score_lead(ScoringConfig(), facts, {})

    assert [rule.id for rule in breakdown.matched] == [
        "budget_known",
        "timeframe_30_days",
        "responded",
        "proposal_requested",
    ]
    assert breakdown.deterministic == 40 + 10 + 20 + 10 + 20


@pytest.mark.parametrize(
    ("score", "priority"),
    [
        (100, Priority.CRITICAL),
        (95, Priority.CRITICAL),
        (94, Priority.HIGH),
        (80, Priority.HIGH),
        (50, Priority.MEDIUM),
        (49, Priority.LOW),
        (0, Priority.LOW),
    ],
)
def test_priority_thresholds(score: int, priority: Priority) -> None:
    assert priority_for(score, PriorityThresholds()) is priority


# --- follow-up ---


def test_follow_up_first_response_window_by_priority() -> None:
    lead = _lead(priority=Priority.HIGH, created_at=NOW - timedelta(hours=3))

    follow_up = next_follow_up(BusinessConfiguration(), lead, NOW)

    assert follow_up is not None
    assert (follow_up.reason, follow_up.overdue, follow_up.due_at) == (
        "first_response",
        False,
        NOW + timedelta(hours=1),
    )


def test_follow_up_after_contact_uses_status_then_priority_interval() -> None:
    contacted = NOW - timedelta(hours=50)
    config = BusinessConfiguration()

    by_status = next_follow_up(config, _lead(status="proposal_sent", last_contact_at=contacted), NOW)
    by_priority = next_follow_up(config, _lead(status="contacted", last_contact_at=contacted), NOW)

    assert by_status is not None and (by_status.reason, by_status.overdue) == ("status", True)
    # No priority counts as medium: 72 hours.
    assert by_priority is not None and (by_priority.reason, by_priority.overdue) == ("interval", False)


def test_closed_leads_need_no_follow_up() -> None:
    assert next_follow_up(BusinessConfiguration(), _lead(status="won"), NOW) is None
    assert next_follow_up(BusinessConfiguration(closed_statuses=["archived"]), _lead(status="won"), NOW) is not None


# --- custom fields ---

DEFINITIONS = [
    CustomFieldDefinition(key="rooms", label="Rooms", type="number"),
    CustomFieldDefinition(key="mortgage", label="Mortgage", type="boolean"),
    CustomFieldDefinition(key="city", label="City", type="text"),
    CustomFieldDefinition(key="move_in", label="Move in", type="date"),
    CustomFieldDefinition(key="kind", label="Kind", type="select", options=["buy", "rent"]),
]


def test_valid_custom_fields_and_undefined_keys_pass() -> None:
    values = {"rooms": 4.5, "mortgage": False, "city": "Haifa", "move_in": "2026-12-01", "kind": "rent", "x": [1]}
    assert custom_field_errors(DEFINITIONS, values) == []
    assert custom_field_errors(DEFINITIONS, dict.fromkeys(("rooms", "kind"))) == []


def test_invalid_custom_fields_are_reported_per_key() -> None:
    values = {"rooms": "4", "mortgage": "yes", "city": 3, "move_in": "next week", "kind": "lease"}

    errors = custom_field_errors(DEFINITIONS, values)

    assert [(error.loc, error.msg) for error in errors] == [
        (["custom_fields", "rooms"], "must be a number"),
        (["custom_fields", "mortgage"], "must be true or false"),
        (["custom_fields", "city"], "must be text"),
        (["custom_fields", "move_in"], "must be a date (YYYY-MM-DD)"),
        (["custom_fields", "kind"], "must be one of: buy, rent"),
    ]


# --- configuration schema ---


@pytest.mark.parametrize(
    "condition",
    [
        {"fact": "favourite_colour", "op": "eq", "value": 1},
        {"fact": "custom_fields.Bad Key", "op": "eq", "value": 1},
        {"fact": "budget", "op": "gt", "value": "1000"},
        {"fact": "budget", "op": "gt", "value": True},
        {"fact": "status", "op": "in", "value": "won"},
        {"fact": "status", "op": "eq", "value": ["won"]},
        {"fact": "status", "op": "eq"},
        {"fact": "status", "op": "exists", "value": "x"},
        {"fact": "status", "op": "like", "value": "x"},
    ],
)
def test_invalid_conditions_are_rejected(condition: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Condition.model_validate(condition)


def test_invalid_configuration_is_rejected() -> None:
    rule = {"id": "a", "label": "A", "points": 1, "when": [{"fact": "replied", "op": "exists"}]}
    for configuration in (
        {"scoring": {"rules": [rule, rule]}},
        {"priority": {"critical": 50, "high": 80, "medium": 10}},
        {"follow_up": {"interval_hours": {"high": 4}}},
        {"closed_statuses": ["Closed Won"]},
        {"unknown": True},
    ):
        with pytest.raises(ValidationError):
            BusinessConfiguration.model_validate(configuration)


def test_settings_update_rejects_bad_definitions() -> None:
    for definitions in (
        [{"key": "a", "label": "A", "type": "text"}, {"key": "a", "label": "B", "type": "number"}],
        [{"key": "kind", "label": "Kind", "type": "select"}],
        [{"key": "city", "label": "City", "type": "text", "options": ["x"]}],
    ):
        with pytest.raises(ValidationError):
            BusinessSettingsUpdate.model_validate({"configuration": {}, "custom_field_definitions": definitions})


def test_stored_settings_that_do_not_parse_fall_back_to_defaults() -> None:
    assert BusinessConfiguration.from_stored({"rules": {"x": 1}}) == BusinessConfiguration()
    assert BusinessConfiguration.from_stored(None) == BusinessConfiguration()
    stored = [{"key": "k"}, {"key": "rooms", "label": "Rooms", "type": "number"}]
    assert [definition.key for definition in stored_definitions(stored)] == ["rooms"]

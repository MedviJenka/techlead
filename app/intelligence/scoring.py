"""Deterministic lead scoring and priority (MAIN_PLAN §48): configured point rules over lead facts."""

from typing import Any

from pydantic import BaseModel

from ai.schemas.enums import Priority
from app.schemas.configuration import (
    CUSTOM_FIELD_PREFIX,
    Condition,
    PriorityThresholds,
    Scalar,
    ScoringConfig,
)


class MatchedRule(BaseModel):
    id: str
    label: str
    points: int


class ScoreBreakdown(BaseModel):
    """How ``final`` was reached. ``ai`` is None until an AI score exists; then it is blended in."""

    base: int
    deterministic: int
    ai: int | None
    ai_weight: float
    final: int
    matched: list[MatchedRule]


def _fact(facts: dict[str, Any], custom_fields: dict[str, Any], name: str) -> Any:
    if name.startswith(CUSTOM_FIELD_PREFIX):
        return custom_fields.get(name.removeprefix(CUSTOM_FIELD_PREFIX))
    return facts.get(name)


def _same(actual: Any, expected: Scalar) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.casefold() == expected.casefold()
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    return bool(actual == expected)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def holds(condition: Condition, actual: Any) -> bool:
    """Whether ``actual`` satisfies the condition. A missing fact satisfies only ``missing`` and ``ne``."""
    op, expected = condition.op, condition.value
    if op == "exists":
        return actual is not None and actual != ""
    if op == "missing":
        return actual is None or actual == ""
    if actual is None:
        return op == "ne"
    if op == "eq":
        return _same(actual, expected)  # type: ignore[arg-type]
    if op == "ne":
        return not _same(actual, expected)  # type: ignore[arg-type]
    if op == "in":
        return any(_same(actual, item) for item in expected)  # type: ignore[union-attr]
    if op == "contains":
        if isinstance(actual, str) and isinstance(expected, str):
            return expected.casefold() in actual.casefold()
        return isinstance(actual, list) and any(_same(item, expected) for item in actual)  # type: ignore[arg-type]
    if not _is_number(actual):
        return False
    number = float(expected)  # type: ignore[arg-type]
    comparisons = {"gt": actual > number, "gte": actual >= number, "lt": actual < number, "lte": actual <= number}
    return bool(comparisons[op])


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def score_lead(
    config: ScoringConfig, facts: dict[str, Any], custom_fields: dict[str, Any], ai_score: int | None = None
) -> ScoreBreakdown:
    matched = [
        MatchedRule(id=rule.id, label=rule.label, points=rule.points)
        for rule in config.rules
        if all(holds(condition, _fact(facts, custom_fields, condition.fact)) for condition in rule.when)
    ]
    deterministic = _clamp(config.base_score + sum(rule.points for rule in matched))
    final = deterministic
    if ai_score is not None:
        final = _clamp(deterministic * (1 - config.ai_weight) + ai_score * config.ai_weight)
    return ScoreBreakdown(
        base=config.base_score,
        deterministic=deterministic,
        ai=ai_score,
        ai_weight=config.ai_weight,
        final=final,
        matched=matched,
    )


def priority_for(score: int, thresholds: PriorityThresholds) -> Priority:
    if score >= thresholds.critical:
        return Priority.CRITICAL
    if score >= thresholds.high:
        return Priority.HIGH
    if score >= thresholds.medium:
        return Priority.MEDIUM
    return Priority.LOW

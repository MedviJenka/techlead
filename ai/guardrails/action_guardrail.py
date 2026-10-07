from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from ai.guardrails.base import Guardrail, Validator, as_guardrail
from ai.schemas import BusinessProfile, NextAction, NextActionRecommendation, Priority

PASSIVE_ACTIONS = frozenset({NextAction.WAIT, NextAction.NURTURE, NextAction.CLOSE_LOST})
CLOCK_SKEW = timedelta(minutes=5)


def make_action_validator(
    business: BusinessProfile,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Validator[NextActionRecommendation]:
    allowed = set(business.ai.allowed_actions)
    needs_approval = set(business.ai.approval_required_actions)

    def validate(rec: NextActionRecommendation) -> list[str]:
        errors: list[str] = []
        if rec.action not in allowed:
            errors.append(f"action '{rec.action}' is not allowed. Choose one of: {', '.join(sorted(allowed))}.")
        if rec.action in needs_approval and not rec.requires_human_approval:
            errors.append(f"action '{rec.action}' requires human approval for this business; set requires_human_approval=true.")
        if rec.action in PASSIVE_ACTIONS and rec.priority == Priority.CRITICAL:
            errors.append(f"priority 'critical' contradicts the passive action '{rec.action}'.")
        if rec.due_at is not None and _as_utc(rec.due_at) < clock() - CLOCK_SKEW:
            errors.append("due_at is in the past; use a future time or null.")
        if not rec.reason.strip():
            errors.append("reason must explain why, what changed and why now.")
        return errors

    return validate


def make_action_guardrail(business: BusinessProfile) -> Guardrail:
    return as_guardrail(NextActionRecommendation, make_action_validator(business))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value

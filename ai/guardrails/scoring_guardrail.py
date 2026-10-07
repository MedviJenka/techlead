from ai.guardrails.base import Guardrail, as_guardrail
from ai.schemas import AIScoreResult

MAX_OVERALL_DEVIATION = 25
MIN_REASONS = 2


def validate_ai_score(result: AIScoreResult) -> list[str]:
    errors: list[str] = []
    if len([r for r in result.reasons if r.strip()]) < MIN_REASONS:
        errors.append(f"Provide at least {MIN_REASONS} concrete reasons for the scores.")
    deviation = abs(result.overall_ai_score - result.component_average)
    if deviation > MAX_OVERALL_DEVIATION:
        errors.append(
            f"overall_ai_score ({result.overall_ai_score}) is {deviation:.0f} points away from the component "
            f"average ({result.component_average:.0f}); keep it within {MAX_OVERALL_DEVIATION} points."
        )
    return errors


scoring_guardrail: Guardrail = as_guardrail(AIScoreResult, validate_ai_score)

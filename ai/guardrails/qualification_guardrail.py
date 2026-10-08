from ai.guardrails.base import Guardrail, as_guardrail
from ai.schemas import QualificationResult

MIN_SUMMARY_CHARS = 20


def validate_qualification(result: QualificationResult) -> list[str]:
    errors: list[str] = []
    if result.qualified and not result.positive_signals:
        errors.append("A qualified lead must list at least one positive signal.")
    if not result.qualified and not (result.negative_signals or result.missing_information):
        errors.append("An unqualified lead must list negative signals or missing information.")
    if len(result.summary.strip()) < MIN_SUMMARY_CHARS:
        errors.append("summary must explain the verdict in at least one full sentence.")
    return errors


qualification_guardrail: Guardrail = as_guardrail(QualificationResult, validate_qualification)

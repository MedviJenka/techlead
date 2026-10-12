"""Adapter from pure validators to CrewAI task guardrails.

Validators are plain functions ``(model) -> list[str]`` returning human-readable violations, which
keeps them unit-testable without CrewAI. ``as_guardrail`` wraps one for ``Task(guardrails=[...])``:
violations are sent back to the agent, which retries up to ``guardrail_max_retries``.
"""

from collections.abc import Callable
from typing import Any

from crewai import TaskOutput
from pydantic import BaseModel, ValidationError

from app.core.logger import Logger

type Validator[M: BaseModel] = Callable[[M], list[str]]
type Guardrail = Callable[[TaskOutput], tuple[bool, Any]]


logger = Logger("guardrails")


def extract_model[M: BaseModel](output: TaskOutput, model: type[M]) -> M:
    """Return the task's structured output, parsing ``raw`` if CrewAI did not convert it."""
    if isinstance(output.pydantic, model):
        return output.pydantic
    return model.model_validate_json(output.raw)


def as_guardrail[M: BaseModel](model: type[M], *validators: Validator[M]) -> Guardrail:
    def guardrail(output: TaskOutput) -> tuple[bool, Any]:
        try:
            result = extract_model(output, model)
        except ValidationError as error:
            logger.fire("guardrail_invalid_output", level="warning", model=model.__name__, errors=error.error_count())
            return False, f"Output must be valid JSON matching {model.__name__}: {error}"
        violations = [v for validator in validators for v in validator(result)]
        if violations:
            logger.fire("guardrail_rejected", level="warning", model=model.__name__, violations=violations)
            return False, "Fix these problems and answer again:\n- " + "\n- ".join(violations)
        # With guardrails attached CrewAI leaves .pydantic unset for string answers; attach the parsed model.
        output.pydantic = result
        output.raw = result.model_dump_json()
        return True, output

    guardrail.__name__ = f"{model.__name__}_guardrail"
    return guardrail

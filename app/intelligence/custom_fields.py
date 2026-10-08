"""Check lead ``custom_fields`` against the business's definitions. Undefined keys pass through unchanged."""

from datetime import date
from typing import Any

from app.schemas.common import RecordError
from app.schemas.configuration import CustomFieldDefinition

MAX_TEXT_LENGTH = 1000


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _problem(definition: CustomFieldDefinition, value: Any) -> str | None:
    """Why ``value`` does not fit the definition, or None. ``None`` always fits (it clears the field)."""
    if value is None:
        return None
    match definition.type:
        case "number":
            ok = isinstance(value, int | float) and not isinstance(value, bool)
            return None if ok else "must be a number"
        case "boolean":
            return None if isinstance(value, bool) else "must be true or false"
        case "text":
            if not isinstance(value, str):
                return "must be text"
            return None if len(value) <= MAX_TEXT_LENGTH else f"must be at most {MAX_TEXT_LENGTH} characters"
        case "date":
            return None if _is_iso_date(value) else "must be a date (YYYY-MM-DD)"
        case "select":
            return None if value in definition.options else f"must be one of: {', '.join(definition.options)}"


def custom_field_errors(definitions: list[CustomFieldDefinition], values: dict[str, Any]) -> list[RecordError]:
    """One error per defined key whose value does not fit, located at ``["custom_fields", key]``."""
    errors = []
    for definition in definitions:
        if definition.key in values and (problem := _problem(definition, values[definition.key])):
            errors.append(RecordError(loc=["custom_fields", definition.key], msg=problem, type="custom_field"))
    return errors

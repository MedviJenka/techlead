"""Per-business deterministic configuration (MAIN_PLAN §4, §48, §52, §53), stored in `businesses` JSONB columns.

`configuration` holds statuses, scoring rules, priority thresholds and follow-up timing. `custom_field_definitions`
types the keys of `leads.custom_fields`. Every section has defaults, so a business with `{}` gets working rules.
"""

import re
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator, model_validator

from ai.schemas.enums import Priority
from app.core.logger import Logger
from app.ingestion.normalize import is_phone_region

logger = Logger(__name__)

MAX_SCORING_RULES = 50
MAX_RULE_CONDITIONS = 5
MAX_CUSTOM_FIELD_DEFINITIONS = 100
MAX_SELECT_OPTIONS = 50
MAX_CLOSED_STATUSES = 20

CUSTOM_FIELD_PREFIX = "custom_fields."
FieldKey = Annotated[str, StringConstraints(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")]
StatusName = Annotated[str, StringConstraints(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Scalar = str | int | float | bool

# Lead facts a scoring condition may test (app/intelligence/facts.py builds them), plus `custom_fields.<key>`.
FACT_NAMES: frozenset[str] = frozenset(
    {
        "status",
        "source",
        "sentiment",
        "has_email",
        "has_phone",
        "has_company",
        "notes",
        "budget",
        "budget_known",
        "timeframe_days",
        "replied",
        "contact_attempts",
        "ignored_follow_ups",
        "days_since_created",
        "days_since_last_contact",
        "proposal_sent",
        "meeting_scheduled",
    }
)
_CUSTOM_FACT = re.compile(rf"^{re.escape(CUSTOM_FIELD_PREFIX)}[a-z][a-z0-9_]*$")

Operator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "exists", "missing"]
_NO_VALUE_OPERATORS = frozenset({"exists", "missing"})
_NUMERIC_OPERATORS = frozenset({"gt", "gte", "lt", "lte"})


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Condition(_Strict):
    """``fact <op> value``. ``exists``/``missing`` take no value; ``in`` takes a list."""

    fact: str = Field(max_length=100)
    op: Operator
    value: Scalar | list[Scalar] | None = None

    @model_validator(mode="after")
    def _valid(self) -> Self:
        if self.fact not in FACT_NAMES and not _CUSTOM_FACT.match(self.fact):
            raise ValueError(f"unknown fact '{self.fact}' (use one of the lead facts or custom_fields.<key>)")
        if self.op in _NO_VALUE_OPERATORS:
            if self.value is not None:
                raise ValueError(f"'{self.op}' takes no value")
        elif self.value is None:
            raise ValueError(f"'{self.op}' needs a value")
        elif self.op == "in" and not isinstance(self.value, list):
            raise ValueError("'in' needs a list value")
        elif self.op != "in" and isinstance(self.value, list):
            raise ValueError(f"'{self.op}' needs a single value, not a list")
        elif self.op in _NUMERIC_OPERATORS and not _is_number(self.value):
            raise ValueError(f"'{self.op}' needs a number")
        return self


class ScoringRule(_Strict):
    """Adds ``points`` (negative to subtract) when every condition holds."""

    id: FieldKey
    label: Label
    points: int = Field(ge=-100, le=100)
    when: list[Condition] = Field(min_length=1, max_length=MAX_RULE_CONDITIONS)


def _rule(rule_id: str, label: str, points: int, fact: str, op: Operator, value: Scalar | None = None) -> ScoringRule:
    return ScoringRule(id=rule_id, label=label, points=points, when=[Condition(fact=fact, op=op, value=value)])


# MAIN_PLAN §48 example rules. "Requested pricing" is read from the lead notes.
DEFAULT_SCORING_RULES: tuple[ScoringRule, ...] = (
    _rule("budget_known", "Budget known", 10, "budget_known", "eq", True),
    _rule("timeframe_30_days", "Purchase within 30 days", 20, "timeframe_days", "lte", 30),
    _rule("responded", "Customer responded", 10, "replied", "eq", True),
    _rule("requested_pricing", "Requested pricing", 15, "notes", "contains", "pricing"),
    _rule("proposal_requested", "Proposal requested or sent", 20, "proposal_sent", "eq", True),
    _rule("no_response_7_days", "No contact for over 7 days", -10, "days_since_last_contact", "gt", 7),
    _rule("ignored_follow_ups", "Four ignored follow-ups", -20, "ignored_follow_ups", "gte", 4),
)


class ScoringConfig(_Strict):
    """``final = deterministic * (1 - ai_weight) + ai * ai_weight`` (MAIN_PLAN §11); deterministic alone without AI."""

    base_score: int = Field(default=40, ge=0, le=100)
    ai_weight: float = Field(default=0.4, ge=0, le=1)
    rules: list[ScoringRule] = Field(default_factory=lambda: list(DEFAULT_SCORING_RULES), max_length=MAX_SCORING_RULES)

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> Self:
        ids = [rule.id for rule in self.rules]
        if duplicates := sorted({rule_id for rule_id in ids if ids.count(rule_id) > 1}):
            raise ValueError(f"duplicate rule ids: {', '.join(duplicates)}")
        return self


class PriorityThresholds(_Strict):
    """Lowest score of each priority; anything below ``medium`` is ``low``."""

    critical: int = Field(default=95, ge=0, le=100)
    high: int = Field(default=80, ge=0, le=100)
    medium: int = Field(default=50, ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.critical >= self.high >= self.medium:
            raise ValueError("thresholds must satisfy critical >= high >= medium")
        return self


def _by_priority(critical: float, high: float, medium: float, low: float) -> dict[Priority, float]:
    return {Priority.CRITICAL: critical, Priority.HIGH: high, Priority.MEDIUM: medium, Priority.LOW: low}


Hours = Annotated[float, Field(gt=0, le=24 * 365)]


class FollowUpConfig(_Strict):
    """When the next contact is due. Leads with no priority are treated as ``medium``."""

    # Never contacted: due this many hours after the lead arrived.
    first_response_hours: dict[Priority, Hours] = Field(default_factory=lambda: _by_priority(1, 4, 24, 48))
    # Contacted: due this many hours after the last contact.
    interval_hours: dict[Priority, Hours] = Field(default_factory=lambda: _by_priority(24, 48, 72, 168))
    # Per-status interval, overriding ``interval_hours`` (e.g. chase a sent proposal after two days).
    status_interval_hours: dict[StatusName, Hours] = Field(default_factory=lambda: {"proposal_sent": 48.0})

    @model_validator(mode="after")
    def _every_priority(self) -> Self:
        for name in ("first_response_hours", "interval_hours"):
            if missing := [p.value for p in Priority if p not in getattr(self, name)]:
                raise ValueError(f"{name} is missing {', '.join(missing)}")
        return self


class BusinessConfiguration(_Strict):
    closed_statuses: list[StatusName] = Field(
        default_factory=lambda: ["won", "lost", "closed_won", "closed_lost"], max_length=MAX_CLOSED_STATUSES
    )
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    priority: PriorityThresholds = Field(default_factory=PriorityThresholds)
    follow_up: FollowUpConfig = Field(default_factory=FollowUpConfig)
    # The business's country (ISO 3166 alpha-2, e.g. "IL"): national phone numbers are stored in E.164 for it.
    phone_region: str | None = None

    @field_validator("phone_region")
    @classmethod
    def _known_region(cls, value: str | None) -> str | None:
        if value is None:
            return None
        region = value.strip().upper()
        if not is_phone_region(region):
            raise ValueError(f"unknown country code: {value}")
        return region

    @classmethod
    def from_stored(cls, value: Any) -> "BusinessConfiguration":
        """The stored JSONB, or the defaults when it does not parse (rows written before this schema existed)."""
        try:
            return cls.model_validate(value or {})
        except ValidationError:
            logger.fire("business_configuration_invalid; using defaults", level="warning")
            return cls()


CustomFieldType = Literal["text", "number", "boolean", "date", "select"]


class CustomFieldDefinition(_Strict):
    """Types one key of ``leads.custom_fields`` (MAIN_PLAN §53). Undefined keys are kept as they arrive."""

    key: FieldKey
    label: Label
    type: CustomFieldType
    options: list[Annotated[str, StringConstraints(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=MAX_SELECT_OPTIONS
    )

    @model_validator(mode="after")
    def _options_only_for_select(self) -> Self:
        if self.type == "select" and not self.options:
            raise ValueError("a select field needs options")
        if self.type != "select" and self.options:
            raise ValueError("only select fields take options")
        return self


def check_unique_keys(definitions: list[CustomFieldDefinition]) -> list[CustomFieldDefinition]:
    keys = [definition.key for definition in definitions]
    if duplicates := sorted({key for key in keys if keys.count(key) > 1}):
        raise ValueError(f"duplicate custom field keys: {', '.join(duplicates)}")
    return definitions


def stored_definitions(value: Any) -> list[CustomFieldDefinition]:
    """Stored definitions; entries that do not parse (written before this schema existed) are skipped."""
    definitions = []
    for entry in value or []:
        try:
            definitions.append(CustomFieldDefinition.model_validate(entry))
        except ValidationError:
            key = entry.get("key") if isinstance(entry, dict) else None
            logger.fire("custom_field_definition_invalid; skipped", level="warning", key=key)
    return definitions


class BusinessSettingsUpdate(_Strict):
    """``PUT /businesses/{id}/settings``: replaces both sections."""

    configuration: BusinessConfiguration
    custom_field_definitions: list[CustomFieldDefinition] = Field(max_length=MAX_CUSTOM_FIELD_DEFINITIONS)

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        check_unique_keys(self.custom_field_definitions)
        return self

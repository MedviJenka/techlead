"""Pure normalization for lead data, shared by manual create and every ingestion adapter.

Each ``normalize_*`` function raises ``ValueError`` on invalid input, so used as Pydantic validators they surface
as ordinary validation errors (422 on the API, a ``failed`` record on import). The ``Annotated`` aliases below are
the only way schemas should apply them, which keeps API input and imported data byte-for-byte identical.

Deliberately dependency-free: no ``email-validator`` / ``phonenumbers`` (recorded in TECH_DEBT).
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field, Strict, StringConstraints

from ai.schemas.enums import Priority, Sentiment

# Column lengths mirrored from db/001_core_tables.sql so oversize input is a 422, not a database error.
EMAIL_MAX_LENGTH = 320
PHONE_MAX_LENGTH = 32
TOKEN_MAX_LENGTH = 50
PHONE_MIN_DIGITS = 7
PHONE_MAX_DIGITS = 15
LONG_TEXT_MAX_LENGTH = 10_000

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_SEPARATORS = re.compile(r"[\s\-.()]")
_TOKEN_SEPARATORS = re.compile(r"[\s\-]+")
_TOKEN_PATTERN = re.compile(r"^[a-z0-9_]+$")


def blank_to_none(value: object) -> object:
    """Strip strings; an empty or whitespace-only string becomes ``None``. Other values pass through."""
    if isinstance(value, str):
        return value.strip() or None
    return value


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > EMAIL_MAX_LENGTH:
        raise ValueError(f"email must be at most {EMAIL_MAX_LENGTH} characters")
    if not _EMAIL_PATTERN.match(email):
        raise ValueError("invalid email address")
    return email


def normalize_phone(value: str) -> str:
    """Keep one optional leading ``+`` and the digits: ``"+972 50-123-4567"`` -> ``"+972501234567"``."""
    compact = _PHONE_SEPARATORS.sub("", value)
    digits = compact.removeprefix("+")
    if not digits.isascii() or not digits.isdigit():
        raise ValueError("phone may contain only digits, spaces, '-', '.', '(', ')' and one leading '+'")
    if not PHONE_MIN_DIGITS <= len(digits) <= PHONE_MAX_DIGITS:
        raise ValueError(f"phone must have {PHONE_MIN_DIGITS}-{PHONE_MAX_DIGITS} digits")
    return compact


def normalize_token(value: str) -> str:
    """Identifier-like values (source, status): ``" Proposal-Sent "`` -> ``"proposal_sent"``."""
    token = _TOKEN_SEPARATORS.sub("_", value.strip().lower())
    if len(token) > TOKEN_MAX_LENGTH:
        raise ValueError(f"must be at most {TOKEN_MAX_LENGTH} characters")
    if not _TOKEN_PATTERN.match(token):
        raise ValueError("may contain only letters, digits, spaces, '-' and '_'")
    return token


def normalize_enum_value(value: object) -> object:
    """Case/whitespace-insensitive enum input; blank becomes ``None``. Membership is checked by the enum type."""
    value = blank_to_none(value)
    return value.lower() if isinstance(value, str) else value


def ensure_utc(value: datetime) -> datetime:
    """Aware datetimes are converted to UTC; naive ones are assumed to already be UTC (TECH_DEBT)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _nullable(normalize: Callable[[str], str]) -> Callable[[object], object]:
    """Before-validator: blank -> None, other strings normalized, non-strings left for type validation."""

    def validator(value: object) -> object:
        value = blank_to_none(value)
        return normalize(value) if isinstance(value, str) else value

    return validator


def _utc_or_none(value: datetime | None) -> datetime | None:
    return None if value is None else ensure_utc(value)


_BlankAsNone = BeforeValidator(blank_to_none)

Email = Annotated[str | None, BeforeValidator(_nullable(normalize_email))]
Phone = Annotated[str | None, BeforeValidator(_nullable(normalize_phone))]
Token50 = Annotated[str, BeforeValidator(_nullable(normalize_token))]
OptionalToken50 = Annotated[str | None, BeforeValidator(_nullable(normalize_token))]
UtcDatetime = Annotated[datetime | None, _BlankAsNone, AfterValidator(_utc_or_none)]
Score = Annotated[int, Strict(), Field(ge=0, le=100)]
PriorityValue = Annotated[Priority | None, BeforeValidator(normalize_enum_value)]
SentimentValue = Annotated[Sentiment | None, BeforeValidator(normalize_enum_value)]

# Free text: stripped, blank -> None, bounded by the column length.
Text50 = Annotated[Annotated[str, StringConstraints(max_length=50)] | None, _BlankAsNone]
Text100 = Annotated[Annotated[str, StringConstraints(max_length=100)] | None, _BlankAsNone]
Text200 = Annotated[Annotated[str, StringConstraints(max_length=200)] | None, _BlankAsNone]
Text255 = Annotated[Annotated[str, StringConstraints(max_length=255)] | None, _BlankAsNone]
LongText = Annotated[Annotated[str, StringConstraints(max_length=LONG_TEXT_MAX_LENGTH)] | None, _BlankAsNone]

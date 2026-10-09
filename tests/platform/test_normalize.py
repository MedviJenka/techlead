"""Pure normalization rules shared by manual create and import (no database)."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from ai.schemas.enums import Priority, Sentiment
from app.ingestion.normalize import (
    Email,
    OptionalToken50,
    Phone,
    PriorityValue,
    Score,
    SentimentValue,
    Text100,
    Token50,
    UtcDatetime,
    blank_to_none,
    ensure_utc,
    normalize_email,
    normalize_phone,
    normalize_token,
    to_e164,
)
from app.schemas.lead import LeadCreate, LeadListParams, LeadUpdate

# --- plain functions ---


@pytest.mark.parametrize(("value", "expected"), [("  x ", "x"), ("", None), ("   ", None), (None, None), (5, 5)])
def test_blank_to_none(value: object, expected: object) -> None:
    assert blank_to_none(value) == expected


def test_email_is_trimmed_and_lowercased() -> None:
    assert normalize_email("  Daniel.Cohen@Example.COM ") == "daniel.cohen@example.com"


@pytest.mark.parametrize(
    "value", ["no-at-sign.com", "with space@example.com", "user@nodot", "a@@b.com", "x" * 310 + "@example.com"]
)
def test_invalid_emails_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_email(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("+972 50-123-4567", "+972501234567"),
        ("050-123-4567", "0501234567"),
        ("(050) 123.4567", "0501234567"),
        ("1234567", "1234567"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_phone_keeps_leading_plus_and_digits(value: str, expected: str) -> None:
    assert normalize_phone(value) == expected


@pytest.mark.parametrize(
    "value",
    ["123456", "1234567890123456", "050-CALL-NOW", "++972501234567", "972+501234567", "+1234567", "+123456789012345"],
)
def test_invalid_phones_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_phone(value)


@pytest.mark.parametrize(
    ("phone", "region", "expected"),
    [
        ("0501234567", "IL", "+972501234567"),
        ("2025550143", "US", "+12025550143"),
        ("+972501234567", "US", "+972501234567"),
        ("0501234567", None, "0501234567"),
        ("12345678901234", "IL", "12345678901234"),
    ],
)
def test_to_e164_reads_national_numbers_in_the_business_country(
    phone: str, region: str | None, expected: str
) -> None:
    assert to_e164(phone, region) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("Website Form", "website_form"), (" Proposal-Sent ", "proposal_sent"), ("NEW", "new"), ("a  b", "a_b")],
)
def test_tokens_are_snake_cased(value: str, expected: str) -> None:
    assert normalize_token(value) == expected


@pytest.mark.parametrize("value", ["web/form", "café", "x" * 51])
def test_invalid_tokens_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_token(value)


def test_ensure_utc_assumes_naive_is_utc_and_converts_offsets() -> None:
    assert ensure_utc(datetime(2026, 10, 7, 8, 0)) == datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
    converted = ensure_utc(datetime(2026, 10, 7, 11, 0, tzinfo=timezone(timedelta(hours=3))))
    assert converted == datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
    assert converted.utcoffset() == timedelta(0)


# --- Annotated aliases (as used by the schemas) ---


def _validate(alias: Any, value: object) -> Any:
    return TypeAdapter(alias).validate_python(value)


@pytest.mark.parametrize("alias", [Email, Phone, OptionalToken50, Text100, UtcDatetime, PriorityValue])
@pytest.mark.parametrize("blank", ["", "   ", None])
def test_optional_aliases_turn_blank_into_none(alias: Any, blank: object) -> None:
    assert _validate(alias, blank) is None


def test_required_token_rejects_blank() -> None:
    with pytest.raises(ValidationError):
        _validate(Token50, "  ")


@pytest.mark.parametrize(
    "value", ["2026-10-07T08:15:22Z", "2026-10-07T11:15:22+03:00", "2026-10-07T08:15:22", "2026-10-07 08:15:22"]
)
def test_utc_datetime_accepts_z_offsets_and_naive(value: str) -> None:
    parsed = _validate(UtcDatetime, value)

    assert parsed == datetime(2026, 10, 7, 8, 15, 22, tzinfo=UTC)
    assert parsed.utcoffset() == timedelta(0)


@pytest.mark.parametrize(("value", "expected"), [("HIGH", Priority.HIGH), (" low ", Priority.LOW)])
def test_priority_is_case_insensitive(value: str, expected: Priority) -> None:
    assert _validate(PriorityValue, value) is expected


def test_sentiment_is_case_insensitive() -> None:
    assert _validate(SentimentValue, "Positive") is Sentiment.POSITIVE


@pytest.mark.parametrize(("alias", "value"), [(PriorityValue, "urgent"), (SentimentValue, "angry")])
def test_unknown_enum_values_are_rejected(alias: Any, value: str) -> None:
    with pytest.raises(ValidationError):
        _validate(alias, value)


@pytest.mark.parametrize("value", [0, 55, 100])
def test_score_accepts_ints_in_range(value: int) -> None:
    assert _validate(Score, value) == value


@pytest.mark.parametrize("value", [-1, 101, "92", True, 92.0])
def test_score_is_strict_and_bounded(value: object) -> None:
    with pytest.raises(ValidationError):
        _validate(Score, value)


def test_text_is_stripped_and_bounded() -> None:
    assert _validate(Text100, "  Daniel ") == "Daniel"
    with pytest.raises(ValidationError):
        _validate(Text100, "x" * 101)


# --- schemas apply the same rules ---


def test_lead_create_normalizes_every_field() -> None:
    lead = LeadCreate.model_validate(
        {
            "source": "Website Form",
            "status": " Proposal-Sent ",
            "priority": "HIGH",
            "first_name": "  ",
            "email": " A@X.COM ",
            "phone": "+972 50-123-4567",
            "last_contact_at": "2026-10-07T12:00:00+03:00",
        }
    )

    assert lead.source == "website_form"
    assert lead.status == "proposal_sent"
    assert lead.priority is Priority.HIGH
    assert lead.first_name is None
    assert lead.email == "a@x.com"
    assert lead.phone == "+972501234567"
    assert lead.last_contact_at == datetime(2026, 10, 7, 9, 0, tzinfo=UTC)


def test_lead_create_defaults_leave_status_and_priority_unset() -> None:
    lead = LeadCreate.model_validate({"source": "web"})

    assert lead.status is None
    assert lead.priority is None
    assert lead.custom_fields == {}


@pytest.mark.parametrize(
    "extra",
    [{"lead_score": 5}, {"raw_payload": {}}, {"business_id": "x"}, {"created_at": "2026-10-07T08:00:00Z"}],
)
def test_lead_create_rejects_server_owned_fields(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        LeadCreate.model_validate({"source": "web"} | extra)


def test_lead_update_rejects_explicit_null_status_but_allows_omitting_it() -> None:
    with pytest.raises(ValidationError):
        LeadUpdate.model_validate({"status": None})

    update = LeadUpdate.model_validate({"notes": "hi"})
    assert update.model_dump(exclude_unset=True) == {"notes": "hi"}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"priority": "urgent"}, {"q": ""}])
def test_list_params_bounds(params: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        LeadListParams.model_validate(params)


def test_list_params_defaults_and_normalization() -> None:
    params = LeadListParams.model_validate({"status": "Proposal Sent", "source": "WhatsApp"})

    assert (params.status, params.source, params.limit, params.offset) == ("proposal_sent", "whatsapp", 25, 0)

"""JsonLeadAdapter: sample-shaped record -> LeadImportData + raw payload + contact history (no database)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from ai.schemas.enums import Channel, Priority, Sentiment
from app.ingestion.adapters import AdaptedLead, ContactHistory, JsonLeadAdapter, record_errors
from app.schemas.common import MAX_JSON_FIELD_BYTES
from tests.platform.factories import load_sample, raw_lead

SAMPLE_IDS = [f"lead_{n:03d}" for n in range(1, 11)]


async def _parse(record: dict[str, Any]) -> AdaptedLead:
    return await JsonLeadAdapter().parse(record)


async def _errors(record: dict[str, Any]) -> list[tuple[list[str | int], str]]:
    with pytest.raises(ValidationError) as excinfo:
        await _parse(record)
    return [(error.loc, error.type) for error in record_errors(excinfo.value)]


async def test_lead_001_maps_every_field() -> None:
    record = raw_lead()

    adapted = await _parse(record)

    data = adapted.data
    assert data.external_id == "lead_001"
    assert (data.source, data.status, data.priority) == ("website_form", "new", Priority.HIGH)
    assert (data.first_name, data.last_name) == ("Daniel", "Cohen")
    assert (data.email, data.phone) == ("daniel.cohen@example.com", "+972501234567")
    assert data.company_name == "Cohen Properties"
    assert data.notes == "Looking for a 4-room apartment in central Tel Aviv."
    assert data.created_at == datetime(2026, 10, 7, 8, 15, 22, tzinfo=UTC)
    assert data.last_contact_at is None
    assert (data.lead_score, data.sentiment) == (92, Sentiment.POSITIVE)
    assert data.ai_summary == "High-intent lead with clear budget and purchase timeframe."
    assert data.recommended_action == "Contact within 1 hour"
    assert data.custom_fields == {
        "product_or_service": "premium apartment",
        "budget": 2500000,
        "currency": "ILS",
        "timeframe": "1-3 months",
        "city": "Tel Aviv",
        "mortgage_approved": True,
    }
    assert adapted.raw_payload == record
    assert adapted.history == ContactHistory(preferred_channel=Channel.WHATSAPP, contact_attempts=0, replied=False)


async def test_raw_payload_is_a_copy() -> None:
    record = raw_lead()

    adapted = await _parse(record)
    record["contact"]["email"] = "changed@example.com"

    assert adapted.raw_payload["contact"]["email"] == "daniel.cohen@example.com"


async def test_all_sample_records_parse() -> None:
    parsed = [await _parse(record) for record in load_sample()["leads"]]

    assert [adapted.data.external_id for adapted in parsed] == SAMPLE_IDS


@pytest.mark.parametrize("index", [1, 3, 6])  # lead_002, lead_004, lead_007
async def test_null_company_maps_to_no_company_name(index: int) -> None:
    assert (await _parse(raw_lead(index))).data.company_name is None


@pytest.mark.parametrize("index", [0, 5, 9])  # lead_001, lead_006, lead_010
async def test_never_contacted_leads_have_no_last_contact(index: int) -> None:
    assert (await _parse(raw_lead(index))).data.last_contact_at is None


async def test_lead_002_contact_history() -> None:
    adapted = await _parse(raw_lead(1))

    assert adapted.data.last_contact_at == datetime(2026, 10, 7, 9, 5, tzinfo=UTC)
    assert adapted.history == ContactHistory(preferred_channel=Channel.PHONE, contact_attempts=1, replied=True)


async def test_unmapped_keys_live_only_in_raw_payload() -> None:
    adapted = await _parse(raw_lead())

    dumped = adapted.data.model_dump()
    for key in ("preferred_channel", "industry", "budget", "currency", "timeframe", "contact_attempts", "replied"):
        assert key not in dumped
    assert adapted.raw_payload["intent"]["budget"] == 2500000


async def test_explicit_custom_fields_win_over_intent_and_nulls_are_dropped() -> None:
    record = raw_lead(1, custom_fields={"timeframe": "next week"})

    adapted = await _parse(record)

    # lead_002 has a null budget: not copied.
    assert adapted.data.custom_fields == {
        "product_or_service": "consultation",
        "currency": "ILS",
        "timeframe": "next week",
    }


async def test_missing_sections_are_tolerated() -> None:
    adapted = await _parse({"lead_id": "x-1", "source": "Web Form"})

    assert adapted.data.source == "web_form"
    assert adapted.data.first_name is None
    assert adapted.data.custom_fields == {}
    assert adapted.history == ContactHistory(preferred_channel=None, contact_attempts=0, replied=False)


async def test_malformed_engagement_metadata_degrades_to_defaults() -> None:
    record = raw_lead(contact={"preferred_channel": "carrier pigeon"}, engagement={"contact_attempts": "3"})

    adapted = await _parse(record)

    assert adapted.history == ContactHistory(preferred_channel=None, contact_attempts=0, replied=False)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"ai": {"lead_score": 101}}, (["ai", "lead_score"], "less_than_equal")),
        ({"ai": {"lead_score": "92"}}, (["ai", "lead_score"], "int_type")),
        ({"priority": "urgent"}, (["priority"], "enum")),
        ({"contact": {"email": "x" * 320 + "@example.com"}}, (["contact", "email"], "value_error")),
        ({"source": "s" * 51}, (["source"], "value_error")),
        ({"ai": {"recommended_action": "x" * 51}}, (["ai", "recommended_action"], "string_too_long")),
        ({"lead_id": 17}, (["lead_id"], "string_type")),
        ({"contact": "x"}, (["contact"], "dict_type")),
        ({"source": None}, (["source"], "string_type")),
        ({"custom_fields": ["not", "a", "dict"]}, (["custom_fields"], "dict_type")),
    ],
)
async def test_invalid_records_report_raw_locations(overrides: dict[str, Any], expected: tuple[Any, str]) -> None:
    assert await _errors(raw_lead(**overrides)) == [expected]


async def test_custom_fields_size_is_capped() -> None:
    record = raw_lead(custom_fields={"blob": "x" * MAX_JSON_FIELD_BYTES})

    assert await _errors(record) == [(["custom_fields"], "value_error")]


async def test_record_errors_keep_messages() -> None:
    with pytest.raises(ValidationError) as excinfo:
        await _parse(raw_lead(ai={"lead_score": 101}))

    [error] = record_errors(excinfo.value)
    assert error.msg == "Input should be less than or equal to 100"

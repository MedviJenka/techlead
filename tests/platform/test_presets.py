"""Industry presets (app/presets.py): a new business starts from its industry's settings and only adjusts them."""

import pytest
from pydantic import ValidationError

from app.intelligence import score_lead
from app.presets import PRESETS, REAL_ESTATE, IndustryPreset
from app.schemas import BusinessCreate
from app.schemas.configuration import BusinessConfiguration
from app.services.business import _to_values


def _create(**fields: object) -> BusinessCreate:
    return BusinessCreate.model_validate({"name": "Haifa Homes", "slug": "haifa-homes"} | fields)


def test_real_estate_preset_fills_what_the_request_leaves_out() -> None:
    values = _to_values(_create(preset="real_estate"))

    assert values["industry"] == "Real estate"
    assert [f["key"] for f in values["custom_field_definitions"]] == [f.key for f in REAL_ESTATE.custom_fields]
    assert values["configuration"] == REAL_ESTATE.configuration.model_dump(mode="json")
    assert values["ai_configuration"]["instructions"] == REAL_ESTATE.instructions
    # Server-controlled policy stays at its defaults: every outbound message needs approval.
    assert "send_whatsapp" in values["ai_configuration"]["approval_required_actions"]


def test_what_the_request_sets_wins_over_the_preset() -> None:
    values = _to_values(
        _create(
            preset="real_estate",
            industry="Luxury real estate",
            configuration={"phone_region": "IL"},
            ai_configuration={"instructions": "Only Tel Aviv penthouses."},
        )
    )
    assert values["industry"] == "Luxury real estate"
    assert values["configuration"] == BusinessConfiguration(phone_region="IL").model_dump(mode="json")
    assert values["ai_configuration"]["instructions"] == "Only Tel Aviv penthouses."
    assert len(values["custom_field_definitions"]) == len(REAL_ESTATE.custom_fields)


def test_without_a_preset_nothing_changes() -> None:
    values = _to_values(_create())
    assert (values["industry"], values["custom_field_definitions"], values["ai_configuration"]["instructions"]) == (
        None, [], None
    )


def test_unknown_presets_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown preset"):
        _create(preset="spaceships")


@pytest.mark.parametrize("preset", PRESETS.values(), ids=list(PRESETS))
def test_preset_rules_only_reference_its_own_custom_fields(preset: IndustryPreset) -> None:
    keys = {f.key for f in preset.custom_fields}
    facts = {c.fact for rule in preset.configuration.scoring.rules for c in rule.when}
    assert {fact.removeprefix("custom_fields.") for fact in facts if fact.startswith("custom_fields.")} <= keys


def test_a_ready_buyer_scores_well_above_a_browser() -> None:
    scoring = REAL_ESTATE.configuration.scoring
    ready = {"budget": 2_500_000.0, "budget_known": True, "timeframe_days": 30, "replied": True}
    ready_fields = {"financing": "pre_approved", "area": "Carmel", "viewing_requested": True}
    browsing = {"budget_known": False, "timeframe_days": None, "replied": False}

    hot = score_lead(scoring, ready, ready_fields, None).final
    cold = score_lead(scoring, browsing, {"financing": "not_started", "property_to_sell": True}, None).final

    assert hot >= 95 and cold <= 30

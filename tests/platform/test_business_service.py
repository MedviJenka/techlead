from typing import Any

import pytest
from pydantic import ValidationError
from supabase import AsyncClient

from ai.schemas import AutonomyLevel
from ai.schemas.business import DEFAULT_APPROVAL_REQUIRED
from app.core.errors import ConflictError
from app.models import Business
from app.repositories import BusinessRepository
from app.schemas import BusinessCreate
from app.schemas.business import MAX_CUSTOM_FIELD_DEFINITIONS
from app.schemas.configuration import BusinessConfiguration
from app.services.business import BusinessService


def _create(**overrides: Any) -> BusinessCreate:
    return BusinessCreate.model_validate({"name": "Acme Solar", "slug": "acme-solar"} | overrides)


# --- schema: AI configuration input (no DB) ---


@pytest.mark.parametrize(
    "policy_field",
    [
        {"autonomy_level": AutonomyLevel.AUTOMATED},
        {"allowed_actions": []},
        {"approval_required_actions": []},
    ],
)
def test_ai_policy_fields_are_not_client_settable(policy_field: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _create(ai_configuration=policy_field)


def test_ai_configuration_applies_server_policy_defaults() -> None:
    data = _create(ai_configuration={"tone": "friendly", "language": "Hebrew"})

    config = data.ai_configuration.to_ai_configuration()

    assert config.tone == "friendly"
    assert config.language == "Hebrew"
    assert config.autonomy_level == AutonomyLevel.DRAFT_ONLY
    assert config.approval_required_actions == list(DEFAULT_APPROVAL_REQUIRED)


@pytest.mark.parametrize(
    "ai_configuration",
    [
        {"tone": "x" * 201},
        {"language": "x" * 51},
        {"instructions": "x" * 4001},
    ],
)
def test_ai_configuration_input_is_bounded(ai_configuration: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _create(ai_configuration=ai_configuration)


# --- schema: timezone, configuration and custom field definitions (no DB) ---


def test_known_timezone_accepted_and_unknown_rejected() -> None:
    assert _create(timezone="Asia/Jerusalem").timezone == "Asia/Jerusalem"
    with pytest.raises(ValidationError):
        _create(timezone="Mars/Olympus")


def test_configuration_defaults_and_rejects_unknown_keys() -> None:
    assert _create().configuration == BusinessConfiguration()
    with pytest.raises(ValidationError):
        _create(configuration={"blob": "x"})


def _definition(index: int) -> dict[str, Any]:
    return {"key": f"field_{index}", "label": f"Field {index}", "type": "text"}


def test_custom_field_definitions_are_capped_and_unique() -> None:
    _create(custom_field_definitions=[_definition(i) for i in range(MAX_CUSTOM_FIELD_DEFINITIONS)])
    with pytest.raises(ValidationError):
        _create(custom_field_definitions=[_definition(i) for i in range(MAX_CUSTOM_FIELD_DEFINITIONS + 1)])
    with pytest.raises(ValidationError, match="duplicate custom field keys: field_1"):
        _create(custom_field_definitions=[_definition(1), _definition(1)])


# --- service (test Supabase project) ---


class _StaleSlugLookupRepository(BusinessRepository):
    """Simulates losing the check-then-insert race: the pre-check misses a row that already exists."""

    async def get_by_slug(self, slug: str) -> Business | None:
        return None


async def test_create_persists_server_controlled_ai_policy(db: AsyncClient) -> None:
    service = BusinessService(BusinessRepository(db))

    business = await service.create(_create(ai_configuration={"instructions": "Be brief."}))

    assert business.ai_configuration["instructions"] == "Be brief."
    assert business.ai_configuration["autonomy_level"] == AutonomyLevel.DRAFT_ONLY
    assert business.ai_configuration["approval_required_actions"] == [a.value for a in DEFAULT_APPROVAL_REQUIRED]


async def test_duplicate_slug_precheck_raises_conflict(db: AsyncClient) -> None:
    service = BusinessService(BusinessRepository(db))
    await service.create(_create())

    with pytest.raises(ConflictError, match="acme-solar"):
        await service.create(_create(name="Other"))


async def test_unique_violation_race_is_translated_to_conflict(db: AsyncClient) -> None:
    await BusinessService(BusinessRepository(db)).create(_create())
    racing = BusinessService(_StaleSlugLookupRepository(db))

    with pytest.raises(ConflictError, match="acme-solar") as exc_info:
        await racing.create(_create(name="Other"))

    assert exc_info.value.__cause__ is not None
    rows = (await db.table("businesses").select("id").eq("slug", "acme-solar").execute()).data
    assert len(rows) == 1

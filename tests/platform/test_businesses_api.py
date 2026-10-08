import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from ai.schemas import AutonomyLevel
from tests.platform.conftest import as_user


def _payload(**overrides: Any) -> dict[str, Any]:
    return {"name": "Acme Solar", "slug": "acme-solar", "industry": "solar", "timezone": "Asia/Jerusalem"} | overrides


async def test_create_and_get_business(client: AsyncClient, api_prefix: str) -> None:
    thresholds = {"critical": 90, "high": 70, "medium": 40}
    created = await client.post(f"{api_prefix}/businesses", json=_payload(configuration={"priority": thresholds}))

    assert created.status_code == 201
    body = created.json()
    assert body["slug"] == "acme-solar"
    assert body["configuration"]["priority"] == thresholds
    assert body["configuration"]["closed_statuses"] == ["won", "lost", "closed_won", "closed_lost"]
    assert body["ai_configuration"]["autonomy_level"] == AutonomyLevel.DRAFT_ONLY

    fetched = await client.get(f"{api_prefix}/businesses/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


async def test_duplicate_slug_is_conflict(client: AsyncClient, api_prefix: str) -> None:
    await client.post(f"{api_prefix}/businesses", json=_payload())

    response = await client.post(f"{api_prefix}/businesses", json=_payload(name="Other"), headers=as_user(uuid.uuid4()))

    assert response.status_code == 409
    assert "acme-solar" in response.json()["error"]["message"]


async def test_creator_becomes_owner_of_one_business(client: AsyncClient, api_prefix: str) -> None:
    assert (await client.get(f"{api_prefix}/me")).json()["business_id"] is None

    created = await client.post(f"{api_prefix}/businesses", json=_payload())
    second = await client.post(f"{api_prefix}/businesses", json=_payload(slug="second"))

    me = (await client.get(f"{api_prefix}/me")).json()
    assert (me["business_id"], me["role"]) == (created.json()["id"], "owner")
    assert second.status_code == 409
    assert second.json()["error"]["message"] == "You already belong to a business"


async def test_other_users_business_is_not_found(client: AsyncClient, api_prefix: str) -> None:
    created = await client.post(f"{api_prefix}/businesses", json=_payload())

    response = await client.get(f"{api_prefix}/businesses/{created.json()['id']}", headers=as_user(uuid.uuid4()))

    assert response.status_code == 404


async def test_unknown_business_is_not_found(client: AsyncClient, api_prefix: str) -> None:
    response = await client.get(f"{api_prefix}/businesses/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        pytest.param({"slug": "Not A Slug"}, "slug", id="bad-slug"),
        pytest.param({"timezone": "Mars/Olympus"}, "timezone", id="bad-timezone"),
        pytest.param({"ai_configuration": {"autonomy_level": 99}}, "autonomy_level", id="bad-autonomy"),
        pytest.param({"unexpected": "field"}, "unexpected", id="extra-field"),
    ],
)
async def test_rejects_invalid_input(
    client: AsyncClient, api_prefix: str, overrides: dict[str, Any], field: str
) -> None:
    response = await client.post(f"{api_prefix}/businesses", json=_payload(**overrides))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in {detail["loc"][-1] for detail in error["details"]}


async def test_unknown_route_uses_error_envelope(client: AsyncClient, api_prefix: str) -> None:
    response = await client.get(f"{api_prefix}/no-such-route")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "http_error", "message": "Not Found"}}


async def test_wrong_method_uses_error_envelope(client: AsyncClient, api_prefix: str) -> None:
    response = await client.delete(f"{api_prefix}/businesses")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "http_error"
    assert "allow" in response.headers


async def test_update_settings_replaces_configuration_and_custom_fields(client: AsyncClient, api_prefix: str) -> None:
    business = (await client.post(f"{api_prefix}/businesses", json=_payload())).json()
    settings = {
        "configuration": {"closed_statuses": ["archived"], "scoring": {"base_score": 10, "rules": []}},
        "custom_field_definitions": [{"key": "rooms", "label": "Rooms", "type": "number"}],
    }

    response = await client.put(f"{api_prefix}/businesses/{business['id']}/settings", json=settings)

    assert response.status_code == 200
    body = response.json()
    assert body["configuration"]["closed_statuses"] == ["archived"]
    assert body["configuration"]["scoring"] == {"base_score": 10, "ai_weight": 0.4, "rules": []}
    assert body["custom_field_definitions"] == [{"key": "rooms", "label": "Rooms", "type": "number", "options": []}]
    assert (await client.get(f"{api_prefix}/businesses/{business['id']}")).json() == body


async def test_update_settings_validates_and_checks_membership(client: AsyncClient, api_prefix: str) -> None:
    business = (await client.post(f"{api_prefix}/businesses", json=_payload())).json()
    path = f"{api_prefix}/businesses/{business['id']}/settings"
    valid = {"configuration": {}, "custom_field_definitions": []}
    bad_rule = {"id": "x", "label": "X", "points": 5, "when": [{"fact": "favourite_colour", "op": "eq", "value": 1}]}

    invalid = await client.put(path, json=valid | {"configuration": {"scoring": {"rules": [bad_rule]}}})
    stranger = await client.put(path, json=valid, headers=as_user(uuid.uuid4()))

    assert invalid.status_code == 422
    assert "unknown fact 'favourite_colour'" in invalid.json()["error"]["message"]
    assert stranger.status_code == 404

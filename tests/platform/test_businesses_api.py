import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from ai.schemas import AutonomyLevel
from tests.platform.conftest import as_user


def _payload(**overrides: Any) -> dict[str, Any]:
    return {"name": "Acme Solar", "slug": "acme-solar", "industry": "solar", "timezone": "Asia/Jerusalem"} | overrides


async def test_create_and_get_business(client: AsyncClient, api_prefix: str) -> None:
    created = await client.post(f"{api_prefix}/businesses", json=_payload(configuration={"rules": {"x": 1}}))

    assert created.status_code == 201
    body = created.json()
    assert body["slug"] == "acme-solar"
    assert body["configuration"] == {"rules": {"x": 1}}
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

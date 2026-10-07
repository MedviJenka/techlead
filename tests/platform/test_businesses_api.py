import uuid
from typing import Any

from httpx import AsyncClient

from ai.schemas import AutonomyLevel


def _payload(**overrides: Any) -> dict[str, Any]:
    return {"name": "Acme Solar", "slug": "acme-solar", "industry": "solar", "timezone": "Asia/Jerusalem"} | overrides


async def test_create_and_get_business(client: AsyncClient) -> None:
    created = await client.post("/api/v1/businesses", json=_payload(configuration={"rules": {"x": 1}}))

    assert created.status_code == 201
    body = created.json()
    assert body["slug"] == "acme-solar"
    assert body["configuration"] == {"rules": {"x": 1}}
    assert body["ai_configuration"]["autonomy_level"] == AutonomyLevel.DRAFT_ONLY

    fetched = await client.get(f"/api/v1/businesses/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


async def test_duplicate_slug_is_conflict(client: AsyncClient) -> None:
    await client.post("/api/v1/businesses", json=_payload())

    response = await client.post("/api/v1/businesses", json=_payload(name="Other"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_unknown_business_is_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/businesses/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_rejects_invalid_input(client: AsyncClient) -> None:
    for bad in (
        _payload(slug="Not A Slug"),
        _payload(timezone="Mars/Olympus"),
        _payload(ai_configuration={"autonomy_level": 99}),
        _payload(unexpected="field"),
    ):
        response = await client.post("/api/v1/businesses", json=bad)
        assert response.status_code == 422, bad

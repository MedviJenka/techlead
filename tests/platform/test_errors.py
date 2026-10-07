"""Domain errors leave the API in the uniform envelope, with optional `details` (no database needed)."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.errors import ConflictError, DomainError, NotFoundError, UnprocessableError
from app.main import create_app


@pytest.fixture
async def raising_client() -> AsyncIterator[AsyncClient]:
    """A real app with one extra route that raises whatever `?kind=` selects."""
    app = create_app()
    errors: dict[str, DomainError] = {
        "conflict": ConflictError("Lead already exists", details={"lead_id": "abc"}),
        "not_found": NotFoundError("Lead x not found"),
        "unprocessable": UnprocessableError("database rejected value", details=[{"loc": ["phone"]}]),
    }

    async def _raise(kind: str) -> None:
        raise errors[kind]

    app.add_api_route("/_test/raise", _raise)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_domain_error_details_are_included(raising_client: AsyncClient) -> None:
    response = await raising_client.get("/_test/raise", params={"kind": "conflict"})

    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "conflict", "message": "Lead already exists", "details": {"lead_id": "abc"}}
    }


async def test_details_key_is_omitted_when_none(raising_client: AsyncClient) -> None:
    response = await raising_client.get("/_test/raise", params={"kind": "not_found"})

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Lead x not found"}}


async def test_unprocessable_error_is_a_422_validation_error(raising_client: AsyncClient) -> None:
    response = await raising_client.get("/_test/raise", params={"kind": "unprocessable"})

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "validation_error",
        "message": "database rejected value",
        "details": [{"loc": ["phone"]}],
    }


def test_domain_error_details_default_to_none() -> None:
    assert NotFoundError("missing").details is None

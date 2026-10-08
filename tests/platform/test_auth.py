"""Login token verification (`app.core.auth`). No database or network: the signing key is a local test key."""

import time
import uuid
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient

from app.core import auth
from app.core.auth import current_user
from app.core.errors import UnauthorizedError
from app.core.supabase import get_supabase
from app.main import create_app
from settings import Settings

PROJECT_URL = "https://test-ref.supabase.co"
ISSUER = f"{PROJECT_URL}/auth/v1"
KEY = ec.generate_private_key(ec.SECP256R1())
USER_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _project(monkeypatch: pytest.MonkeyPatch) -> None:
    config = Settings(OPENAI_MODEL="test-model", SUPABASE_PROJECT_URL=PROJECT_URL)
    monkeypatch.setattr(auth, "get_config", lambda: config)

    async def _signing_key(_: str) -> Any:
        return KEY.public_key()

    monkeypatch.setattr(auth, "signing_key", _signing_key)


def _token(key: ec.EllipticCurvePrivateKey = KEY, **claims: Any) -> str:
    now = int(time.time())
    payload = {
        "sub": str(USER_ID),
        "email": "a@example.com",
        "aud": "authenticated",
        "iss": ISSUER,
        "iat": now,
        "exp": now + 60,
    }
    return jwt.encode(payload | claims, key, algorithm="ES256")


async def _verify(token: str) -> auth.AuthUser:
    return await current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))


async def test_valid_token_gives_the_user() -> None:
    user = await _verify(_token())

    assert (user.id, user.email) == (USER_ID, "a@example.com")


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_token(exp=int(time.time()) - 10), id="expired"),
        pytest.param(_token(aud="anon"), id="wrong-audience"),
        pytest.param(_token(iss="https://other.supabase.co/auth/v1"), id="other-project"),
        pytest.param(_token(key=ec.generate_private_key(ec.SECP256R1())), id="wrong-key"),
        pytest.param("not-a-jwt", id="garbage"),
    ],
)
async def test_invalid_tokens_are_rejected(token: str) -> None:
    with pytest.raises(UnauthorizedError):
        await _verify(token)


async def test_api_requires_sign_in_except_health() -> None:
    app = create_app()
    app.dependency_overrides[get_supabase] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/businesses/{uuid.uuid4()}")
        bad = await client.get(f"/api/v1/businesses/{uuid.uuid4()}", headers={"Authorization": "Bearer x"})

    assert response.status_code == bad.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

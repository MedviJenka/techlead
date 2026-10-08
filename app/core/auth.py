"""Who is calling: the Supabase Auth access token the frontend sends as ``Authorization: Bearer <token>``.

Users sign in with Google through Supabase Auth in the browser; the backend only verifies the resulting token
against the project's public keys (JWKS). No Google credentials are needed here.
"""

import asyncio
import uuid
from functools import cache
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.errors import UnauthorizedError
from settings import get_config

_ALGORITHMS = ["ES256", "RS256"]
_AUDIENCE = "authenticated"


class AuthUser(BaseModel):
    id: uuid.UUID
    email: str | None
    name: str | None = None


@cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    """Fetches the public keys once and caches them (refetched when a token names an unknown key)."""
    return jwt.PyJWKClient(url)


async def signing_key(token: str) -> jwt.PyJWK:
    """The project's public key that signed ``token``. Blocking HTTP on a cache miss, so off the event loop."""
    _, jwks_url = get_config().supabase_auth_urls()
    return await asyncio.to_thread(_jwks_client(jwks_url).get_signing_key_from_jwt, token)


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))],
) -> AuthUser:
    """FastAPI dependency: the signed-in user, or 401."""
    if credentials is None:
        raise UnauthorizedError("Sign in required")
    token = credentials.credentials
    issuer, _ = get_config().supabase_auth_urls()
    try:
        key = await signing_key(token)
        claims = jwt.decode(token, key, algorithms=_ALGORITHMS, audience=_AUDIENCE, issuer=issuer)
        metadata = claims.get("user_metadata") or {}
        return AuthUser(id=claims["sub"], email=claims.get("email"), name=metadata.get("full_name"))
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise UnauthorizedError("Invalid or expired session") from exc


CurrentUser = Annotated[AuthUser, Depends(current_user)]

import json
from functools import cache
from typing import Annotated, Any, Optional
from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_origins(value: Any) -> Any:
    """Accept CORS origins as a JSON list (``["http://a", "http://b"]``) or CSV (``http://a,http://b``)."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped.startswith('['):
        return json.loads(stripped)
    return [origin.strip() for origin in stripped.split(',') if origin.strip()]


class Settings(BaseSettings):

    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    APP_ENV:                     str           = Field(default='dev',  description='')
    API_VERSION:                 str           = Field(default='v1',   description='version segment of the API prefix (/api/{API_VERSION})')
    GOOGLE_SHEETS:               Optional[str] = Field(default=None,   description='')
    OPENAI_MODEL:                str           = Field(...,            description='')
    AI_REASONING_MODEL:          Optional[str] = Field(default=None,   description='model for qualification/strategy agents; falls back to OPENAI_MODEL')
    AI_FAST_MODEL:               Optional[str] = Field(default=None,   description='model for extraction/classification agents; falls back to OPENAI_MODEL')
    OPENAI_API_KEY:              Optional[str] = Field(default=None,   description='')
    LOGFIRE_TOKEN:               Optional[str] = Field(default=None,   description='')
    SUPABASE_PROJECT_URL:        Optional[str] = Field(default=None,   description='Supabase project URL (https://<ref>.supabase.co); the app database')
    SUPABASE_PUBLISHABLE_KEY:    Optional[str] = Field(default=None,   description='public key; given to the frontend (Google sign-in), not used by the backend')
    SUPABASE_SECRET_KEY:         Optional[str] = Field(default=None,   description='secret (service_role) key the backend uses for every database call; keep server-side')
    SUPABASE_JWKS_URL:           Optional[str] = Field(default=None,   description='Supabase Auth public keys, to verify user login tokens; defaults to <SUPABASE_PROJECT_URL>/auth/v1/.well-known/jwks.json')
    TEST_SUPABASE_URL:           Optional[str] = Field(default=None,   description='separate Supabase project wiped by pytest; never the app project')
    TEST_SUPABASE_SECRET_KEY:    Optional[str] = Field(default=None,   description='secret key of the TEST_SUPABASE_URL project')
    CORS_ORIGINS:                Annotated[list[str], NoDecode, BeforeValidator(_parse_origins)] = Field(default=['http://localhost:5173'], description='frontend origins allowed by CORS (JSON list or comma-separated)')

    @property
    def api_prefix(self) -> str:
        """Single source of truth for the API mount point, e.g. ``/api/v1``."""
        return f'/api/{self.API_VERSION}'

    def supabase_auth_urls(self) -> tuple[str, str]:
        """(token issuer, JWKS URL) of the project's Supabase Auth."""
        if not self.SUPABASE_PROJECT_URL:
            raise ValueError('SUPABASE_PROJECT_URL must be set to verify login tokens')
        issuer = f"{self.SUPABASE_PROJECT_URL.rstrip('/')}/auth/v1"
        return issuer, self.SUPABASE_JWKS_URL or f'{issuer}/.well-known/jwks.json'

    def supabase_credentials(self) -> tuple[str, str]:
        """(project URL, secret key) for the backend's Supabase client."""
        if not self.SUPABASE_PROJECT_URL or not self.SUPABASE_SECRET_KEY:
            raise ValueError('SUPABASE_PROJECT_URL and SUPABASE_SECRET_KEY must be set (the database is always Supabase)')
        return self.SUPABASE_PROJECT_URL, self.SUPABASE_SECRET_KEY


@cache
def get_config() -> Settings:
    """Load settings on first use so importing modules never requires a configured environment."""
    return Settings()

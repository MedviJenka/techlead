import json
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Optional
from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_origins(value: Any) -> Any:
    """Accept CORS origins as a JSON list"""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped.startswith('['):
        return json.loads(stripped)
    return [origin.strip() for origin in stripped.split(',') if origin.strip()]


CORS_TYPE = Annotated[list[str], NoDecode, BeforeValidator(_parse_origins)]


class Settings(BaseSettings):

    model_config = SettingsConfigDict(env_file=Path(__file__).parent / ".env", extra="allow")

    APP_ENV:                             str             = Field(default='dev',description='')
    API_VERSION:                         str             = Field(default='v1', description='version segment of the API prefix (/api/{API_VERSION})')
    VERBOSE:                             bool            = Field(default=True, description='crew ai agent verbose')
    GOOGLE_SHEETS:                       Optional[str]   = Field(default=None, description='')
    OPENAI_MODEL:                        str             = Field(...,          description='')
    AI_REASONING_MODEL:                  Optional[str]   = Field(default=None, description='model for qualification/strategy agents; falls back to OPENAI_MODEL')
    AI_FAST_MODEL:                       Optional[str]   = Field(default=None, description='model for extraction/classification agents; falls back to OPENAI_MODEL')
    AI_PRICE_INPUT_PER_MTOK:             Optional[float] = Field(default=None, description="USD per million prompt tokens of the reasoning model; with the output price, each AI run's cost is recorded in dollars")
    AI_PRICE_CACHED_INPUT_PER_MTOK:      Optional[float] = Field(default=None, description='USD per million cached prompt tokens; unset bills them at the input price')
    AI_PRICE_OUTPUT_PER_MTOK:            Optional[str]   = Field(default=None, description='USD per million completion tokens of the reasoning model')
    AI_TEMPERATURE:                      Optional[str]   = Field(default=None, description="sampling temperature for every agent; unset sends none (reasoning models such as gpt-5 reject anything but the default)")
    OPENAI_API_KEY:                      Optional[str]   = Field(default=None, description='')
    LOGFIRE_TOKEN:                       Optional[str]   = Field(default=None, description='')
    SUPABASE_PROJECT_URL:                Optional[str]   = Field(default=None, description='Supabase project URL (https://<ref>.supabase.co); the app database')
    SUPABASE_PUBLISHABLE_KEY:            Optional[str]   = Field(default=None, description='public key; given to the frontend (Google sign-in), not used by the backend')
    SUPABASE_SECRET_KEY:                 Optional[str]   = Field(default=None, description='secret (service_role) key the backend uses for every database call; keep server-side')
    SUPABASE_JWKS_URL:                   Optional[str]   = Field(default=None, description='Supabase Auth public keys, to verify user login tokens; defaults to <SUPABASE_PROJECT_URL>/auth/v1/.well-known/jwks.json')
    TEST_SUPABASE_URL:                   Optional[str]   = Field(default=None, description='separate Supabase project wiped by pytest; never the app project')
    TEST_SUPABASE_SECRET_KEY:            Optional[str]   = Field(default=None, description='secret key of the TEST_SUPABASE_URL project')
    TEST_SUPABASE_PUBLISHABLE_KEY:       Optional[str]   = Field(default=None, description='publishable key of the TEST_SUPABASE_URL project; pytest checks it cannot touch the tables')
    SUPABASE_S3_STORAGE:                 Optional[str]   = Field(default=None, description='Supabase Storage S3 endpoint (https://<ref>.storage.supabase.co/storage/v1/s3)')
    SUPABASE_REGION:                     Optional[str]   = Field(default=None, description='region shown next to the S3 endpoint in Supabase > Storage > S3')
    SUPABASE_S3_ACCESS_KEY_ID:           Optional[str]   = Field(default=None, description='Supabase Storage S3 access key id; keep server-side')
    SUPABASE_S3_SECRET_ACCESS_KEY:       Optional[str]   = Field(default=None, description='Supabase Storage S3 secret access key; keep server-side')
    AI_MEMORY_BUCKET:                    Optional[str]   = Field(default=None, description='private bucket for per-agent CrewAI memory; unset turns agent memory off')
    AI_MEMORY_CACHE_DIR:                 Path            = Field(default=Path('.ai_memory'), description='local directory agents run their memory out of; synced to AI_MEMORY_BUCKET')
    WHATSAPP_ACCESS_TOKEN:               Optional[str]   = Field(default=None, description='WhatsApp Cloud API token (Meta system user) that sends messages for every connected number; keep server-side')
    WHATSAPP_APP_SECRET:                 Optional[str]   = Field(default=None, description='Meta app secret: verifies the X-Hub-Signature-256 of every webhook; unset rejects all webhooks')
    WHATSAPP_VERIFY_TOKEN:               Optional[str]   = Field(default=None, description='any secret string, also entered in the Meta app webhook settings (subscription handshake)')
    WHATSAPP_GRAPH_VERSION:              str             = Field(default='v23.0', description='Graph API version of the WhatsApp Cloud API')
    WHATSAPP_GRAPH_URL:                  str             = Field(default='https://graph.facebook.com', description='base URL of the Graph API; http://localhost:8001 sends to the local mock (python -m app.api.v1.mock)')
    WHATSAPP_APPROVAL_TEMPLATE:          Optional[str]   = Field(default=None, description='approved message template (body {{1}} lead, {{2}} draft; 3 quick-reply buttons) sent to an owner outside the 24h window')
    WHATSAPP_APPROVAL_TEMPLATE_LANGUAGE: str             = Field(default='en', description='language code of WHATSAPP_APPROVAL_TEMPLATE')
    CORS_ORIGINS:                        CORS_TYPE       = Field(default=['http://localhost:5173'], description='frontend origins allowed by CORS (JSON list or comma-separated)')

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


Config = get_config()

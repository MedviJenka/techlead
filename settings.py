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
    SUPABASE_PROJECT_URL:        Optional[str] = Field(default=None,   description='Supabase REST URL (https://...); not a database URL')
    SUPABASE_PUBLISHABLE_KEY:    Optional[str] = Field(default=None,   description='')
    SUPABASE_SQL_CONNECT_STRING: Optional[str] = Field(default=None,   description="the application's PostgreSQL connection string (Supabase)")
    DB_TRANSACTION_POOLER:       bool          = Field(default=False,  description="set when SUPABASE_SQL_CONNECT_STRING points at Supabase's transaction-mode pooler (port 6543)")
    DB_ECHO:                     bool          = Field(default=False,  description='log every SQL statement')
    CORS_ORIGINS:                Annotated[list[str], NoDecode, BeforeValidator(_parse_origins)] = Field(default=['http://localhost:5173'], description='frontend origins allowed by CORS (JSON list or comma-separated)')

    @property
    def api_prefix(self) -> str:
        """Single source of truth for the API mount point, e.g. ``/api/v1``."""
        return f'/api/{self.API_VERSION}'

    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async URL (postgresql+asyncpg://...) built from SUPABASE_SQL_CONNECT_STRING."""
        url = self.SUPABASE_SQL_CONNECT_STRING
        if not url:
            raise ValueError('SUPABASE_SQL_CONNECT_STRING must be set (the application database is always Supabase)')
        scheme, _, rest = url.partition('://')
        return f'postgresql+asyncpg://{rest}' if scheme in {'postgres', 'postgresql'} else url


@cache
def get_config() -> Settings:
    """Load settings on first use so importing modules never requires a configured environment."""
    return Settings()

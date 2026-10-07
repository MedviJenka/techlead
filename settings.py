from functools import cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    APP_ENV:                     str           = Field(default='dev',  description='')
    API_VERSION:                 str           = Field(default='v1',   description='')
    GOOGLE_SHEETS:               str | None = Field(default=None,   description='')
    OPENAI_MODEL:                str           = Field(...,            description='')
    AI_REASONING_MODEL:          str | None = Field(default=None,   description='model for qualification/strategy agents; falls back to OPENAI_MODEL')
    AI_FAST_MODEL:               str | None = Field(default=None,   description='model for extraction/classification agents; falls back to OPENAI_MODEL')
    OPENAI_API_KEY:              str | None = Field(default=None,   description='')
    LOGFIRE_TOKEN:               str | None = Field(default=None,   description='')
    SUPABASE_PROJECT_URL:        str | None = Field(default=None,   description='')
    SUPABASE_PUBLISHABLE_KEY:    str | None = Field(default=None,   description='')
    SUPABASE_SQL_CONNECT_STRING: str | None = Field(default=None,   description='')
    DATABASE_URL:                str | None = Field(default=None,   description='PostgreSQL URL; falls back to SUPABASE_SQL_CONNECT_STRING')
    DB_ECHO:                     bool          = Field(default=False,  description='log every SQL statement')
    CORS_ORIGINS:                list[str]     = Field(default=['http://localhost:5173'], description='frontend origins allowed by CORS')

    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async URL (postgresql+asyncpg://...) built from DATABASE_URL or the Supabase string."""
        url = self.DATABASE_URL or self.SUPABASE_SQL_CONNECT_STRING
        if not url:
            raise ValueError('DATABASE_URL (or SUPABASE_SQL_CONNECT_STRING) must be set')
        scheme, _, rest = url.partition('://')
        return f'postgresql+asyncpg://{rest}' if scheme in {'postgres', 'postgresql'} else url


@cache
def get_config() -> Settings:
    """Load settings on first use so importing cellenium never requires a configured environment."""
    return Settings()


Config = get_config()

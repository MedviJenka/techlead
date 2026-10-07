"""Pure unit tests for `settings.Settings` and the destructive-fixture guard; no database or `.env` needed."""

from typing import Any

import pytest

from settings import Settings
from tests.platform.conftest import unsafe_test_database_reason


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("SUPABASE_SQL_CONNECT_STRING", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    kwargs: dict[str, Any] = {"_env_file": None, "OPENAI_MODEL": "test-model"}
    return Settings(**kwargs)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param('["http://a.test", "http://b.test"]', ["http://a.test", "http://b.test"], id="json"),
        pytest.param("http://a.test, http://b.test", ["http://a.test", "http://b.test"], id="csv"),
        pytest.param("http://a.test", ["http://a.test"], id="single"),
    ],
)
def test_cors_origins_accepts_json_and_csv(monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]) -> None:
    assert _settings(monkeypatch, CORS_ORIGINS=raw).CORS_ORIGINS == expected


def test_cors_origins_default(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch).CORS_ORIGINS == ["http://localhost:5173"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("postgres://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db", id="postgres"),
        pytest.param("postgresql://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db", id="postgresql"),
        pytest.param("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db", id="already-async"),
    ],
)
def test_async_database_url_rewrites_scheme(monkeypatch: pytest.MonkeyPatch, raw: str, expected: str) -> None:
    assert _settings(monkeypatch, SUPABASE_SQL_CONNECT_STRING=raw).async_database_url == expected


def test_async_database_url_requires_supabase_string(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="SUPABASE_SQL_CONNECT_STRING"):
        _ = _settings(monkeypatch).async_database_url


def test_api_prefix_follows_api_version(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch, API_VERSION="v2").api_prefix == "/api/v2"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://techlead:techlead@localhost:5433/techlead_test",
        "postgresql+asyncpg://u:p@127.0.0.1/other_test",
    ],
)
def test_guard_accepts_local_test_database(url: str) -> None:
    assert unsafe_test_database_reason(url) is None


@pytest.mark.parametrize(
    ("url", "fragment"),
    [
        pytest.param("postgresql+asyncpg://u:p@localhost:5433/techlead", "must end with '_test'", id="prod-name"),
        pytest.param("postgresql+asyncpg://u:p@localhost:5433", "must end with '_test'", id="no-database"),
        pytest.param("postgresql://u:p@db.abc.supabase.co:5432/app_test", "Supabase", id="supabase-co"),
        pytest.param("postgresql://u:p@aws-0-eu.pooler.supabase.com:6543/x_test", "Supabase", id="pooler"),
        pytest.param("postgresql://u:p@my-pooler.internal/x_test", "Supabase", id="any-pooler"),
        pytest.param("not a url", "not a valid", id="garbage"),
    ],
)
def test_guard_rejects_unsafe_database(url: str, fragment: str) -> None:
    reason = unsafe_test_database_reason(url)

    assert reason is not None
    assert fragment in reason

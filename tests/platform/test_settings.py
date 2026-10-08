"""Pure unit tests for `settings.Settings` and the destructive-fixture guard; no database or `.env` needed."""

from typing import Any

import pytest

from settings import Settings
from tests.platform.conftest import unsafe_test_project_reason


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    for key in ("SUPABASE_PROJECT_URL", "SUPABASE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
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


def test_supabase_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, SUPABASE_PROJECT_URL="https://abc.supabase.co", SUPABASE_SECRET_KEY="sb_secret_x")

    assert settings.supabase_credentials() == ("https://abc.supabase.co", "sb_secret_x")


def test_supabase_credentials_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="SUPABASE_SECRET_KEY"):
        _settings(monkeypatch, SUPABASE_PROJECT_URL="https://abc.supabase.co").supabase_credentials()


def test_api_prefix_follows_api_version(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch, API_VERSION="v2").api_prefix == "/api/v2"


APP = "https://appref.supabase.co"


def test_guard_accepts_separate_project() -> None:
    assert unsafe_test_project_reason("https://testref.supabase.co", APP) is None


@pytest.mark.parametrize(
    ("url", "fragment"),
    [
        pytest.param("https://appref.supabase.co", "app's own", id="same"),
        pytest.param("HTTPS://AppRef.supabase.co/", "app's own", id="same-normalized"),
        pytest.param("http://127.0.0.1:54321", "must be a Supabase project URL", id="local"),
    ],
)
def test_guard_rejects_unsafe_project(url: str, fragment: str) -> None:
    reason = unsafe_test_project_reason(url, APP)

    assert reason is not None
    assert fragment in reason

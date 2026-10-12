"""Sanity checks for the signed-out landing page, driven by cellenium.

Locators live in the cellenium Google Sheet, worksheet tab ``Landing``. The tests skip
unless that sheet is configured (``GOOGLE_SHEETS`` and ``CREDENTIALS_JSON`` in ``.env``)
and the frontend is reachable at ``LANDING_URL`` (default: the Vite dev server).
"""

import os
from collections.abc import Iterator
from pathlib import Path
import httpx
import pytest
from cellenium.engine.page_engine import PageEngine
from playwright.sync_api import expect


LANDING_URL = os.environ.get("LANDING_URL", "http://localhost:5173/")


VALUE_PROPS = ["Never miss a hot lead", "AI-drafted follow-ups you approve", "Every lead's story in one timeline"]


def _skip_reason() -> str | None:
    from cellenium.settings import get_config

    try:
        config = get_config()
    except Exception as error:
        return f"cellenium is not configured: {error}"
    if not Path(config.CREDENTIALS_JSON).is_file():
        return f"cellenium credentials file {config.CREDENTIALS_JSON} is missing"
    try:
        httpx.get(LANDING_URL, timeout=3)
    except httpx.HTTPError:
        return f"frontend is not running at {LANDING_URL}"
    return None


@pytest.fixture(scope="module")
def landing() -> Iterator[PageEngine]:
    if reason := _skip_reason():
        pytest.skip(reason)
    engine = PageEngine(screen='LandingPage')
    try:
        engine.get_web(LANDING_URL)
        yield engine
    finally:
        engine.teardown()


def test_page_title(landing: PageEngine) -> None:
    expect(landing.page).to_have_title("Techlead")


def test_headline(landing: PageEngine) -> None:
    expect(landing.wait_for_element("headline")).to_contain_text("We make sure you do not lose them.")


def test_value_props(landing: PageEngine) -> None:
    expect(landing.get_element("value_props").locator("li")).to_have_text(VALUE_PROPS)


def test_sign_in_card(landing: PageEngine) -> None:
    expect(landing.wait_for_element("sign_in_title")).to_have_text("Sign in to your workspace")
    expect(landing.get_element("terms")).to_contain_text("Terms of Service and Privacy Policy")


def test_google_button_is_ready(landing: PageEngine) -> None:
    button = landing.wait_for_element("google_button")
    expect(button).to_have_text("Continue with Google")
    expect(button).to_be_enabled()

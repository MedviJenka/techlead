import os
import pytest
from datetime import UTC, datetime


os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
# Tests never ship logs to Logfire, even when .env holds a token.
os.environ["LOGFIRE_TOKEN"] = ""

from ai.data.sample_store import SAMPLE_BUSINESS, InMemoryLeadStore, load_sample_store
from ai.factory import BusinessCrewFactory, SkillLibrary
from ai.schemas import BusinessProfile, LeadSnapshot
from tests.fakes import ScriptedLLM

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
BUSINESS_ID = SAMPLE_BUSINESS.id


@pytest.fixture(scope="session")
def skill_library() -> SkillLibrary:
    return SkillLibrary()


@pytest.fixture
def store() -> InMemoryLeadStore:
    return load_sample_store(clock=lambda: NOW)


@pytest.fixture
def business(store: InMemoryLeadStore) -> BusinessProfile:
    return store.get_business(BUSINESS_ID)


@pytest.fixture
def tomer(store: InMemoryLeadStore) -> LeadSnapshot:
    return store.get_lead(BUSINESS_ID, "lead_008")


def make_factory(store: InMemoryLeadStore, llm: ScriptedLLM, skills: SkillLibrary) -> BusinessCrewFactory:
    return BusinessCrewFactory(store, lambda tier: llm, skills)

"""Runs the CrewAI LeadIntelligenceCrew for one lead (MAIN_PLAN §64). The application decides what to keep.

CrewAI is imported lazily: the API starts, and every other route works, without loading it.
"""

import asyncio
from functools import cache
from typing import TYPE_CHECKING, Protocol

from ai.schemas import ActivitySnapshot, BusinessProfile, LeadSnapshot

if TYPE_CHECKING:
    from ai.config import LLMResolver
    from ai.crews.lead_intelligence.crew import LeadIntelligenceResult
    from ai.factory import SkillLibrary


class AnalysisEngine(Protocol):
    async def analyze(
        self, business: BusinessProfile, lead: LeadSnapshot, activities: list[ActivitySnapshot]
    ) -> "LeadIntelligenceResult": ...


@cache
def _skills() -> "SkillLibrary":
    from ai.factory import SkillLibrary

    return SkillLibrary()  # reads every SKILL.md once per process


class CrewAnalysisEngine:
    """The configured LLM (``OPENAI_MODEL`` / ``AI_*_MODEL``). Each call makes real, billed LLM requests.

    ``llm_resolver`` replaces the configured models (tests pass a scripted LLM).
    """

    def __init__(self, llm_resolver: "LLMResolver | None" = None) -> None:
        self._llm_resolver = llm_resolver

    async def analyze(
        self, business: BusinessProfile, lead: LeadSnapshot, activities: list[ActivitySnapshot]
    ) -> "LeadIntelligenceResult":
        from ai.config import LLMSettings
        from ai.factory import BusinessCrewFactory
        from app.analysis.read_service import SingleLeadReadService

        service = SingleLeadReadService(business, lead, activities)
        resolver = self._llm_resolver or LLMSettings.from_env().resolver()
        factory = BusinessCrewFactory(service, resolver, _skills())
        crew = factory.lead_intelligence_crew(business.id)
        # kickoff() is synchronous and slow (several LLM calls): keep it off the event loop.
        return await asyncio.to_thread(crew.analyze, lead, activities)

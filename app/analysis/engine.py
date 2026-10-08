"""Runs the CrewAI LeadIntelligenceCrew for one lead (MAIN_PLAN §64). The application decides what to keep.

CrewAI is imported lazily: the API starts, and every other route works, without loading it.
"""

import asyncio
import time
from functools import cache
from typing import TYPE_CHECKING, Protocol
from ai.schemas import ActivitySnapshot, BusinessProfile, LeadSnapshot
from app.core.logging import Logger

if TYPE_CHECKING:
    from ai.config import LLMResolver
    from ai.crews.lead_intelligence.crew import LeadIntelligenceResult
    from ai.factory import SkillLibrary

logger = Logger(__name__)


class AnalysisEngine(Protocol):

    async def analyze(self, business: BusinessProfile, lead: LeadSnapshot, activities: list[ActivitySnapshot]) -> "LeadIntelligenceResult": ...


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
        logger.fire("crew_kickoff", business_id=business.id, lead_id=lead.id, activities=len(activities))
        started = time.perf_counter()
        try:
            # kickoff() is synchronous and slow (several LLM calls): keep it off the event loop.
            result = await asyncio.to_thread(crew.analyze, lead, activities)
        except Exception as exc:
            elapsed = round(time.perf_counter() - started, 2)
            logger.fire("crew_failed", level="error", _exc_info=exc, lead_id=lead.id, elapsed_s=elapsed)
            raise
        logger.fire("crew_finished", lead_id=lead.id, elapsed_s=round(time.perf_counter() - started, 2))
        return result

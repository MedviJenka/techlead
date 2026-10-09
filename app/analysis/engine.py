"""Runs the CrewAI LeadIntelligenceCrew for one lead (MAIN_PLAN §64). The application decides what to keep.

CrewAI is imported lazily: the API starts, and every other route works, without loading it.
"""

import asyncio
import time
from typing import TYPE_CHECKING, Protocol

from ai.schemas import ActivitySnapshot, BusinessProfile, LeadSnapshot
from app.core.logger import Logger
from settings import Settings

if TYPE_CHECKING:
    from ai.config import LLMResolver
    from ai.crews.lead_intelligence.crew import LeadIntelligenceResult

logger = Logger(__name__)


def reasoning_model(config: Settings) -> str:
    return config.AI_REASONING_MODEL or config.OPENAI_MODEL


def missing_ai_configuration(config: Settings) -> str | None:
    """Why the crew cannot run here, or None. OpenAI models (the default provider) need ``OPENAI_API_KEY``."""
    model = reasoning_model(config)
    if (model.startswith("openai/") or "/" not in model) and not config.OPENAI_API_KEY:
        return "AI analysis is not configured: set OPENAI_API_KEY"
    return None


class AnalysisEngine(Protocol):

    async def analyze(
        self, business: BusinessProfile, lead: LeadSnapshot, activities: list[ActivitySnapshot]
    ) -> "LeadIntelligenceResult": ...


class CrewAnalysisEngine:
    """The configured LLM (``OPENAI_MODEL`` / ``AI_*_MODEL``). Each call makes real, billed LLM requests.

    ``llm_resolver`` replaces the configured models (tests pass a scripted LLM).
    """

    def __init__(self, llm_resolver: "LLMResolver | None" = None) -> None:
        self._llm_resolver = llm_resolver

    async def analyze(
        self, business: BusinessProfile, lead: LeadSnapshot, activities: list[ActivitySnapshot]
    ) -> "LeadIntelligenceResult":
        from ai.crews import AIRuntime, LeadIntelligenceCrew
        from app.analysis.read_service import SingleLeadReadService

        service = SingleLeadReadService(business, lead, activities)
        if self._llm_resolver is None:
            runtime = AIRuntime.from_env(service)
        else:
            runtime = AIRuntime(service, self._llm_resolver)
        crew = LeadIntelligenceCrew(business, runtime)
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

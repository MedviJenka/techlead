"""Drafts a reply to a lead with the CrewAI ConversationCrew (MAIN_PLAN §44). A draft is never sent by itself.

CrewAI is imported lazily, as in ``app.analysis.engine``: only the worker image has it.
"""

import asyncio
import time
from typing import TYPE_CHECKING, Protocol

from ai.schemas import ActivitySnapshot, BusinessProfile, Channel, FollowupDraft, LeadSnapshot, NextActionRecommendation
from app.core.logger import Logger

if TYPE_CHECKING:
    from ai.config import LLMResolver

logger = Logger("drafting")


class ReplyDrafter(Protocol):
    async def draft(
        self,
        business: BusinessProfile,
        lead: LeadSnapshot,
        activities: list[ActivitySnapshot],
        recommendation: NextActionRecommendation | None,
    ) -> FollowupDraft: ...


class CrewReplyDrafter:
    """The configured LLM (real, billed requests); ``llm_resolver`` replaces it (tests pass a scripted LLM)."""

    def __init__(self, llm_resolver: "LLMResolver | None" = None, channel: Channel = Channel.WHATSAPP) -> None:
        self._llm_resolver = llm_resolver
        self._channel = channel

    async def draft(
        self,
        business: BusinessProfile,
        lead: LeadSnapshot,
        activities: list[ActivitySnapshot],
        recommendation: NextActionRecommendation | None,
    ) -> FollowupDraft:
        from ai.crews import AIRuntime, ConversationCrew
        from app.analysis.read_service import SingleLeadReadService

        service = SingleLeadReadService(business, lead, activities)
        runtime = AIRuntime.from_env(service) if self._llm_resolver is None else AIRuntime(service, self._llm_resolver)
        crew = ConversationCrew(business, runtime)
        started = time.perf_counter()
        draft = await asyncio.to_thread(
            crew.draft_followup, lead, self._channel, recommendation=recommendation, activities=activities
        )
        logger.fire("reply_drafted", lead_id=lead.id, elapsed_s=round(time.perf_counter() - started, 2))
        return draft

"""Least-privilege agent policy (MAIN_PLAN §43): which skills, tools and model tier each agent gets.

Every tool here is read-only and bound to one business. No agent has write access; the application
validates and executes whatever an agent proposes.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ai.schemas import ModelTier
from ai.tools import (
    BusinessScopedTool,
    GetBusinessConfigurationTool,
    GetBusinessMetricsTool,
    GetLeadActivitiesTool,
    GetLeadTool,
    SearchBusinessLeadsTool,
)


@dataclass(frozen=True)
class AgentPolicy:
    skills: tuple[str, ...]
    tools: tuple[type[BusinessScopedTool], ...]
    tier: ModelTier
    business_context: bool = True  # attach industry + business-specific skills


AGENT_POLICIES: Mapping[str, AgentPolicy] = MappingProxyType({
    "qualification_agent": AgentPolicy(
        skills=("lead-qualification", "conversation-analysis"),
        tools=(GetLeadTool, GetLeadActivitiesTool, GetBusinessConfigurationTool),
        tier=ModelTier.REASONING,
    ),
    "scoring_agent": AgentPolicy(
        skills=("lead-scoring", "objection-handling"),
        tools=(GetLeadActivitiesTool,),
        tier=ModelTier.REASONING,
    ),
    "next_action_agent": AgentPolicy(
        skills=("sales-reasoning", "objection-handling"),
        tools=(GetLeadActivitiesTool, GetBusinessConfigurationTool),
        tier=ModelTier.REASONING,
    ),
    "conversation_agent": AgentPolicy(
        skills=("conversation-analysis", "objection-handling"),
        tools=(GetLeadTool, GetLeadActivitiesTool),
        tier=ModelTier.FAST,
    ),
    "followup_agent": AgentPolicy(
        skills=("follow-up-strategy", "objection-handling"),
        tools=(GetLeadActivitiesTool, GetBusinessConfigurationTool),
        tier=ModelTier.REASONING,
    ),
    "sales_manager_agent": AgentPolicy(
        skills=("sales-reasoning", "churn-risk"),
        tools=(SearchBusinessLeadsTool, GetLeadActivitiesTool, GetBusinessMetricsTool),
        tier=ModelTier.REASONING,
    ),
    "business_query_agent": AgentPolicy(
        skills=(),
        tools=(GetBusinessConfigurationTool,),
        tier=ModelTier.FAST,
        business_context=False,
    ),
})

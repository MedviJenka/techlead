from collections.abc import Iterable

from ai.config import LLMResolver
from ai.crews.base import AgentResources, CrewContext
from ai.crews.conversation.crew import ConversationCrew
from ai.crews.lead_intelligence.crew import LeadIntelligenceCrew
from ai.crews.management.crew import ManagementCrew
from ai.factory.policy import AGENT_POLICIES
from ai.factory.skills import SkillLibrary
from ai.ports import LeadReadService
from ai.schemas import BusinessProfile

LEAD_INTELLIGENCE_AGENTS = ("qualification_agent", "scoring_agent", "next_action_agent")
CONVERSATION_AGENTS = ("conversation_agent", "followup_agent")
MANAGEMENT_AGENTS = ("business_query_agent", "sales_manager_agent")


class BusinessCrewFactory:
    """Builds crews customized per business: generic + industry + business skills, scoped tools, tiered LLMs.

    Same agent code for every customer; only configuration differs (MAIN_PLAN §46).
    """

    def __init__(
        self,
        service: LeadReadService,
        llm_resolver: LLMResolver,
        skills: SkillLibrary | None = None,
        *,
        verbose: bool = False,
    ) -> None:
        self._service = service
        self._llm = llm_resolver
        self._skills = skills or SkillLibrary()
        self._verbose = verbose

    def lead_intelligence_crew(self, business_id: str) -> LeadIntelligenceCrew:
        return LeadIntelligenceCrew(self.build_context(business_id, LEAD_INTELLIGENCE_AGENTS))

    def conversation_crew(self, business_id: str) -> ConversationCrew:
        return ConversationCrew(self.build_context(business_id, CONVERSATION_AGENTS))

    def management_crew(self, business_id: str) -> ManagementCrew:
        return ManagementCrew(self.build_context(business_id, MANAGEMENT_AGENTS))

    def build_context(self, business_id: str, agent_names: Iterable[str]) -> CrewContext:
        business = self._service.get_business(business_id)
        agents = {name: self._agent_resources(name, business) for name in agent_names}
        return CrewContext(business=business, agents=agents, verbose=self._verbose)

    def _agent_resources(self, name: str, business: BusinessProfile) -> AgentResources:
        policy = AGENT_POLICIES[name]
        return AgentResources(
            llm=self._llm(policy.tier),
            tools=[tool.bind(self._service, business.id) for tool in policy.tools],
            skills=self._skills.compose(policy.skills, business, business_context=policy.business_context),
        )

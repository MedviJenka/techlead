from crewai import Agent
from crewai.skills.models import Skill

from ai.crews import BusinessCrew, ConversationCrew, LeadIntelligenceCrew, ManagementCrew
from ai.data.sample_store import InMemoryLeadStore
from ai.tools import BusinessScopedTool
from tests.conftest import BUSINESS_ID, make_crew
from tests.fakes import ScriptedLLM

CREWS: tuple[type[BusinessCrew], ...] = (LeadIntelligenceCrew, ConversationCrew, ManagementCrew)


def all_agents(store: InMemoryLeadStore) -> dict[str, Agent]:
    """Every @agent of every crew, built for the sample business."""
    agents: dict[str, Agent] = {}
    for crew_class in CREWS:
        crew = make_crew(crew_class, store, ScriptedLLM({}))
        for name in crew.__crew_metadata__["original_agents"]:  # type: ignore[attr-defined]
            agents[name] = getattr(crew, name)()
    return agents


def test_every_agent_builds_with_prompts_and_its_crew_skills(store: InMemoryLeadStore) -> None:
    agents = all_agents(store)
    assert len(agents) == 7
    for name, agent in agents.items():
        assert agent.role and agent.goal, name
        assert agent.skills and all(isinstance(skill, Skill) for skill in agent.skills), name


def test_agents_only_get_read_only_business_scoped_tools(store: InMemoryLeadStore) -> None:
    for name, agent in all_agents(store).items():
        for tool in agent.tools or []:
            assert isinstance(tool, BusinessScopedTool), name
            assert tool.business_id == BUSINESS_ID, name
            assert not type(tool).__name__.startswith(("Update", "Send", "Delete", "Create")), name

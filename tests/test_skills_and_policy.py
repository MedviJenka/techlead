import pytest
from crewai import Agent

from ai.crews import BusinessCrew, ConversationCrew, LeadIntelligenceCrew, ManagementCrew
from ai.data.sample_store import InMemoryLeadStore
from ai.schemas import AIConfiguration, BusinessProfile
from ai.skill_library import SKILLS_ROOT, InvalidConfigurationError, SkillLibrary
from ai.tools import BusinessScopedTool
from tests.conftest import BUSINESS_ID, make_crew
from tests.fakes import ScriptedLLM

CREWS: tuple[type[BusinessCrew], ...] = (LeadIntelligenceCrew, ConversationCrew, ManagementCrew)


def all_agents(store: InMemoryLeadStore, skills: SkillLibrary) -> dict[str, Agent]:
    """Every @agent of every crew, built for the sample business: unknown skills raise here."""
    agents: dict[str, Agent] = {}
    for crew_class in CREWS:
        crew = make_crew(crew_class, store, ScriptedLLM({}), skills)
        for name in crew.__crew_metadata__["original_agents"]:  # type: ignore[attr-defined]
            agents[name] = getattr(crew, name)()
    return agents

MVP_SKILLS = {"lead-qualification", "lead-scoring", "sales-reasoning", "conversation-analysis",
              "follow-up-strategy", "objection-handling", "churn-risk", "real-estate", "automotive", "insurance"}


def test_all_skills_load_with_instructions(skill_library: SkillLibrary) -> None:
    assert MVP_SKILLS <= skill_library.names
    for name in MVP_SKILLS:
        assert skill_library.get(name).instructions


def test_every_agent_builds_and_has_prompts(store: InMemoryLeadStore, skill_library: SkillLibrary) -> None:
    agents = all_agents(store, skill_library)
    assert len(agents) == 7
    for name, agent in agents.items():
        assert agent.role and agent.goal, name


def test_compose_adds_industry_and_business_skills(skill_library: SkillLibrary) -> None:
    agency = BusinessProfile(id="b", slug="acme-solar", name="ACME", industry="real_estate",
                             ai=AIConfiguration(extra_skills=["churn-risk"]))
    names = [s.name for s in skill_library.compose(["lead-qualification", "lead-qualification"], agency)]
    assert names == ["lead-qualification", "real-estate", "churn-risk", "acme-solar"]


def test_same_agents_different_expertise(skill_library: SkillLibrary) -> None:
    dealer = BusinessProfile(id="b", slug="dealer", name="Dealer", industry="automotive")
    names = {s.name for s in skill_library.compose(["lead-qualification"], dealer)}
    assert "automotive" in names and "real-estate" not in names


def test_business_context_can_be_disabled(skill_library: SkillLibrary) -> None:
    agency = BusinessProfile(id="b", slug="acme-solar", name="ACME", industry="real_estate")
    assert skill_library.compose([], agency, business_context=False) == []


def test_unknown_configured_skill_is_rejected(skill_library: SkillLibrary) -> None:
    broken = BusinessProfile(id="b", slug="b", name="B", ai=AIConfiguration(extra_skills=["does-not-exist"]))
    with pytest.raises(InvalidConfigurationError):
        skill_library.compose([], broken)


def test_business_skills_are_not_shared_skills(skill_library: SkillLibrary) -> None:
    assert "techlead" not in skill_library.names
    assert skill_library.business_skill("techlead") is not None
    assert (SKILLS_ROOT / "businesses" / "techlead" / "SKILL.md").is_file()


def test_agents_only_get_read_only_business_scoped_tools(
    store: InMemoryLeadStore, skill_library: SkillLibrary
) -> None:
    for name, agent in all_agents(store, skill_library).items():
        for tool in agent.tools or []:
            assert isinstance(tool, BusinessScopedTool), name
            assert tool.business_id == BUSINESS_ID, name
            assert not type(tool).__name__.startswith(("Update", "Send", "Delete", "Create")), name

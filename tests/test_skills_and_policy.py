import pytest

from ai.factory import AGENT_POLICIES, InvalidConfigurationError, SkillLibrary
from ai.factory.skills import SKILLS_ROOT
from ai.schemas import AIConfiguration, BusinessProfile
from ai.tools import BusinessScopedTool

MVP_SKILLS = {"lead-qualification", "lead-scoring", "sales-reasoning", "conversation-analysis",
              "follow-up-strategy", "objection-handling", "churn-risk", "real-estate", "automotive", "insurance"}


def test_all_skills_load_with_instructions(skill_library: SkillLibrary) -> None:
    assert MVP_SKILLS <= skill_library.names
    for name in MVP_SKILLS:
        assert skill_library.get(name).instructions


def test_every_policy_skill_exists(skill_library: SkillLibrary) -> None:
    for policy in AGENT_POLICIES.values():
        for name in policy.skills:
            skill_library.get(name)


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


def test_agents_only_get_read_only_business_scoped_tools() -> None:
    for name, policy in AGENT_POLICIES.items():
        for tool in policy.tools:
            assert issubclass(tool, BusinessScopedTool), name
            assert not tool.__name__.startswith(("Update", "Send", "Delete", "Create")), name

from collections.abc import Iterable
from pathlib import Path

from crewai.skills.loader import activate_skill, discover_skills
from crewai.skills.models import Skill

from ai.schemas import BusinessProfile

SKILLS_ROOT = Path(__file__).resolve().parent / "skills"
BUSINESS_SKILLS_DIR = "businesses"


class InvalidConfigurationError(ValueError):
    """A business configuration references something that does not exist."""


class SkillLibrary:
    """Loads SKILL.md files once and composes per-agent skill sets.

    Layout: ``<root>/<skill-name>/SKILL.md`` for generic and industry skills and
    ``<root>/businesses/<business-slug>/SKILL.md`` for business-specific skills.
    """

    def __init__(self, root: Path = SKILLS_ROOT) -> None:
        self._shared = _load_dir(root)
        business_dir = root / BUSINESS_SKILLS_DIR
        self._business = _load_dir(business_dir) if business_dir.is_dir() else {}

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._shared)

    def get(self, name: str) -> Skill:
        try:
            return self._shared[name]
        except KeyError:
            raise InvalidConfigurationError(f"Unknown skill '{name}'") from None

    def industry_skill(self, industry: str | None) -> Skill | None:
        if not industry:
            return None
        return self._shared.get(industry.strip().lower().replace("_", "-"))

    def business_skill(self, slug: str) -> Skill | None:
        return self._business.get(slug)

    def compose(self, generic: Iterable[str], business: BusinessProfile, *, business_context: bool = True) -> list[Skill]:
        """generic skills + industry skill + business extra skills + business-specific skill, de-duplicated."""
        skills = [self.get(name) for name in generic]
        if business_context:
            skills.append(self.industry_skill(business.industry))
            skills.extend(self.get(name) for name in business.ai.extra_skills)
            skills.append(self.business_skill(business.slug))
        unique: dict[str, Skill] = {}
        for skill in skills:
            if skill is not None:
                unique.setdefault(skill.name, skill)
        return list(unique.values())


def _load_dir(path: Path) -> dict[str, Skill]:
    return {skill.name: activate_skill(skill) for skill in discover_skills(path)}

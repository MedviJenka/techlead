from pydantic import BaseModel, Field, model_validator

from ai.schemas.enums import AutonomyLevel, NextAction

DEFAULT_APPROVAL_REQUIRED: tuple[NextAction, ...] = (
    NextAction.SEND_WHATSAPP,
    NextAction.SEND_EMAIL,
    NextAction.SEND_PROPOSAL,
    NextAction.CLOSE_LOST,
)


class ScoringWeights(BaseModel):
    """Blend between deterministic and AI scoring. The application owns the final score."""

    deterministic_weight: float = Field(default=0.6, ge=0, le=1)
    ai_weight: float = Field(default=0.4, ge=0, le=1)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "ScoringWeights":
        if abs(self.deterministic_weight + self.ai_weight - 1.0) > 1e-6:
            raise ValueError("deterministic_weight + ai_weight must equal 1.0")
        return self


class AIConfiguration(BaseModel):
    """Per-business knobs that shape agent behaviour without forking code."""

    tone: str = Field(default="professional, warm and concise")
    language: str = Field(default="English")
    autonomy_level: AutonomyLevel = AutonomyLevel.DRAFT_ONLY
    allowed_actions: list[NextAction] = Field(default_factory=lambda: list(NextAction))
    approval_required_actions: list[NextAction] = Field(default_factory=lambda: list(DEFAULT_APPROVAL_REQUIRED))
    instructions: str | None = Field(default=None, description="Free-text business instructions for agents")
    auto_analyze: bool = Field(default=True, description="Run the AI analysis (NewLeadFlow) on every new lead")


class BusinessProfile(BaseModel):
    """Read model of a business (tenant) as seen by the AI layer."""

    id: str
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str
    industry: str | None = None
    timezone: str = "UTC"
    ai: AIConfiguration = Field(default_factory=AIConfiguration)
    scoring: ScoringWeights = Field(default_factory=ScoringWeights)

    def render_rules(self) -> str:
        """Compact, prompt-friendly description of the business's AI rules."""
        lines = [
            f"Business: {self.name} (industry: {self.industry or 'unspecified'}, timezone: {self.timezone})",
            f"Autonomy level: {self.ai.autonomy_level.value} ({self.ai.autonomy_level.name})",
            f"Allowed next actions: {', '.join(a.value for a in self.ai.allowed_actions)}",
            f"Actions that require human approval: {', '.join(a.value for a in self.ai.approval_required_actions)}",
            f"Communication tone: {self.ai.tone}; language: {self.ai.language}",
        ]
        if self.ai.instructions:
            lines.append(f"Business instructions: {self.ai.instructions}")
        return "\n".join(lines)

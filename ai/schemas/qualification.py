from pydantic import BaseModel, Field

from ai.schemas.enums import FitLevel, IntentLevel, Urgency


class QualificationResult(BaseModel):
    """Output of QualifyLeadTask (MAIN_PLAN §19)."""

    qualified: bool = Field(description="Does the lead match the business's sales criteria?")
    confidence: float = Field(ge=0, le=1, description="Confidence in the verdict, 0.0-1.0")
    intent: IntentLevel = Field(description="Strength of buying intent")
    urgency: Urgency = Field(description="How soon the lead needs a solution")
    fit: FitLevel = Field(description="How well the lead matches the ideal customer profile")
    missing_information: list[str] = Field(default_factory=list, description="Facts needed to qualify with certainty")
    positive_signals: list[str] = Field(default_factory=list, description="Evidence supporting qualification")
    negative_signals: list[str] = Field(default_factory=list, description="Evidence against qualification")
    summary: str = Field(description="Two to three sentence explanation of the verdict")

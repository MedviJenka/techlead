from pydantic import BaseModel, Field


class AIScoreResult(BaseModel):
    """Subjective AI component of lead scoring (MAIN_PLAN §20). Never the authoritative final score."""

    intent_score: int = Field(ge=0, le=100, description="Strength of buying intent, 0-100")
    urgency_score: int = Field(ge=0, le=100, description="Time pressure to buy, 0-100")
    fit_score: int = Field(ge=0, le=100, description="Match with the ideal customer profile, 0-100")
    engagement_score: int = Field(ge=0, le=100, description="Quality of engagement so far, 0-100")
    sentiment_score: int = Field(ge=0, le=100, description="Customer sentiment, 0 (hostile) - 100 (enthusiastic)")
    overall_ai_score: int = Field(ge=0, le=100, description="Holistic AI assessment, 0-100")
    reasons: list[str] = Field(description="Concrete evidence behind the scores")

    @property
    def component_average(self) -> float:
        parts = (self.intent_score, self.urgency_score, self.fit_score, self.engagement_score, self.sentiment_score)
        return sum(parts) / len(parts)

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class Anomaly(BaseModel):
    """One concrete problem in the evaluated response, backed by a quote."""

    kind:        str      = Field(description="hallucination, missed_fact, wrong_value, policy_violation, "
                                              "wrong_language, tone, format or other")
    severity:    Severity
    evidence:    str      = Field(description="The exact words from the evaluated response, or the missing fact")
    explanation: str      = Field(description="Why this is wrong, citing the source context")


class CriterionScore(BaseModel):
    name:    str = Field(description="Rubric criterion, e.g. faithfulness, completeness, policy")
    score:   int = Field(ge=0, le=10)
    comment: str


class ResponseEvaluation(BaseModel):
    """An LLM judge's verdict on one AI response. ``passed`` is decided here, not by the judge."""

    score:            int                  = Field(ge=0, le=100, description="Overall quality of the response")
    confidence_level: float                = Field(ge=0, le=1, description="How sure the judge is of this evaluation")
    criteria:         list[CriterionScore] = Field(min_length=1)
    anomalies:        list[Anomaly]        = Field(default_factory=list)
    output_notice:    str                  = Field(description="Two or three sentences a reviewer reads first")

    def passed(self, min_score: int = 70) -> bool:
        """A high or critical anomaly fails the response whatever its score."""
        blocking = {Severity.HIGH, Severity.CRITICAL}
        return self.score >= min_score and not any(anomaly.severity in blocking for anomaly in self.anomalies)

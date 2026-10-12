import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from ai.schemas import AIScoreResult, NextActionRecommendation, QualificationResult
from app.core.logger import Logger
from app.models import Activity, AnalysisJobStatus, AnalysisTrigger

logger = Logger("analysis-schema")


class AnalysisResult(Protocol):
    """What one AI run produced (``LeadIntelligenceResult`` in ai/crews/lead_intelligence)."""

    @property
    def qualification(self) -> QualificationResult: ...

    @property
    def ai_score(self) -> AIScoreResult: ...

    @property
    def recommendation(self) -> NextActionRecommendation: ...


@dataclass(frozen=True)
class RunCost:
    """Tokens and LLM requests of one AI run, and their price when the model's prices are configured."""

    model: str
    prompt_tokens: int
    cached_prompt_tokens: int
    completion_tokens: int
    requests: int
    cost_usd: Decimal | None

    def as_metadata(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "cached_prompt_tokens": self.cached_prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "requests": self.requests,
            "cost_usd": None if self.cost_usd is None else str(self.cost_usd),
        }


class AnalysisJobRead(BaseModel):
    """A queued or finished AI run. ``pending``/``running`` is the lead's ``analysis_pending`` state (MAIN_PLAN §58)."""

    id: uuid.UUID
    lead_id: uuid.UUID
    trigger: AnalysisTrigger
    status: AnalysisJobStatus
    attempts: int
    max_attempts: int
    run_after: datetime
    last_error: str | None
    cost_usd: Decimal | None
    created_at: datetime
    finished_at: datetime | None


class SavedAnalysis(BaseModel):
    """The AI's latest saved view of a lead (its ``ai_analysis`` activity).

    The recommendation is advice. Its ``priority`` is the AI's opinion; the lead's priority stays the score-based one.
    """

    analysed_at: datetime
    qualification: QualificationResult
    ai_score: AIScoreResult
    recommendation: NextActionRecommendation

    @classmethod
    def from_activity(cls, activity: Activity) -> "SavedAnalysis | None":
        """None for an activity written before the full result was stored, or one that no longer parses."""
        try:
            return cls(
                analysed_at=activity.created_at,
                qualification=activity.metadata["qualification"],
                ai_score=activity.metadata["score"],
                recommendation=activity.metadata["recommendation"],
            )
        except (KeyError, ValidationError):
            logger.fire("saved_analysis_unreadable", level="warning", activity_id=str(activity.id))
            return None


class LeadAnalysisState(BaseModel):
    """``GET /leads/{lead_id}/analysis``: the latest job (poll it while open) and the latest saved analysis."""

    job: AnalysisJobRead | None
    result: SavedAnalysis | None

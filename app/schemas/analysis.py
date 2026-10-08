from pydantic import BaseModel

from ai.schemas import AIScoreResult, NextActionRecommendation, QualificationResult
from app.schemas.lead import LeadRead


class LeadAnalysis(BaseModel):
    """``POST /leads/{lead_id}/analyze``: the saved lead and what the crew proposed.

    The recommendation is advice. Its ``priority`` is the AI's opinion; the lead's priority stays the score-based one.
    """

    lead: LeadRead
    qualification: QualificationResult
    ai_score: AIScoreResult
    recommendation: NextActionRecommendation

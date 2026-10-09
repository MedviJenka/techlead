"""Quality evaluation of LeadIntelligenceCrew against the sample leads (MAIN_PLAN §60, §64).

Unlike the unit tests, an evaluation run makes real, billed LLM calls: ``python -m ai.evals``.
"""

from ai.evals.cases import LEAD_INTELLIGENCE_CASES, RANKING, EvalCase
from ai.evals.runner import CaseResult, EvalReport, check_case, check_ranking, run_lead_intelligence_eval

__all__ = [
    "LEAD_INTELLIGENCE_CASES",
    "RANKING",
    "CaseResult",
    "EvalCase",
    "EvalReport",
    "check_case",
    "check_ranking",
    "run_lead_intelligence_eval",
]

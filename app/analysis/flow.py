"""NewLeadFlow (MAIN_PLAN §65): what happens to a saved lead, run by the worker as a background job.

    Lead saved → qualification → AI scoring → next action    (LeadIntelligenceCrew: one run, tasks share context)
               → deterministic scoring → final score → priority   (LeadService.record_analysis, under the lock)
               → priority route

The orchestration is plain Python, not a CrewAI Flow: every step after the crew is deterministic (MAIN_PLAN §80).
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from ai.schemas import Priority
from app.analysis.cost import TokenPrices, run_cost
from app.analysis.engine import AnalysisEngine
from app.analysis.snapshots import to_activity_snapshot, to_business_profile, to_lead_snapshot
from app.core.logger import Logger
from app.models import Lead
from app.schemas.analysis import RunCost
from app.services.lead import LeadService

logger = Logger(__name__)


class LeadRoute(StrEnum):
    """Where the scored lead goes next. Phase 7 attaches actions (owner alert, first-reply draft) to each route."""

    HOT = "hot"  # critical or high: respond now
    WARM = "warm"  # medium: follow up on the normal cadence
    COLD = "cold"  # low or unscored: nurture


_ROUTES = {
    Priority.CRITICAL: LeadRoute.HOT,
    Priority.HIGH: LeadRoute.HOT,
    Priority.MEDIUM: LeadRoute.WARM,
    Priority.LOW: LeadRoute.COLD,
}


def route_for(priority: Priority | None) -> LeadRoute:
    return _ROUTES[priority] if priority else LeadRoute.COLD


@dataclass(frozen=True)
class FlowOutcome:
    lead: Lead
    route: LeadRoute
    cost: RunCost | None


class NewLeadFlow:
    def __init__(self, service: LeadService, engine: AnalysisEngine, model: str, prices: TokenPrices | None) -> None:
        self._service = service
        self._engine = engine
        self._model = model
        self._prices = prices

    async def run(self, business_id: uuid.UUID, lead_id: uuid.UUID) -> FlowOutcome:
        """Raises when the AI or the database fails; the lead itself is never touched in that case."""
        business, lead, activities = await self._service.analysis_inputs(business_id, lead_id)
        result = await self._engine.analyze(
            to_business_profile(business),
            to_lead_snapshot(lead, activities),
            [to_activity_snapshot(activity) for activity in activities],
        )
        cost = run_cost(self._model, getattr(result, "usage", None), self._prices)
        saved = await self._service.record_analysis(business_id, lead_id, result, cost)
        route = route_for(saved.priority)
        logger.fire(
            "lead_routed",
            business_id=str(business_id),
            lead_id=str(lead_id),
            route=route.value,
            lead_score=saved.lead_score,
            priority=saved.priority,
            cost_usd=None if cost is None or cost.cost_usd is None else str(cost.cost_usd),
        )
        return FlowOutcome(saved, route, cost)

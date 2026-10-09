import logging
from collections.abc import Sequence
from crewai import Agent, Crew, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.types.usage_metrics import UsageMetrics
from pydantic import BaseModel
from ai.crews.base import BusinessCrew, task_result
from ai.guardrails import make_action_guardrail, qualification_guardrail, scoring_guardrail
from ai.schemas import (
    ActivitySnapshot,
    AIScoreResult,
    LeadSnapshot,
    ModelTier,
    NextActionRecommendation,
    QualificationResult,
)
from ai.schemas.lead import render_activities
from ai.tools import GetBusinessConfigurationTool, GetLeadActivitiesTool, GetLeadTool

logger = logging.getLogger(__name__)


class LeadIntelligenceResult(BaseModel):
    qualification: QualificationResult
    ai_score: AIScoreResult
    recommendation: NextActionRecommendation
    usage: UsageMetrics | None = None  # token usage of the whole run; not part of the AI's answer


@CrewBase
class LeadIntelligenceCrew(BusinessCrew):
    """Qualification → AI scoring → next-action recommendation for a single lead (MAIN_PLAN §44, §64)."""

    @agent
    def qualification_agent(self) -> Agent:
        return self.make_agent(
            "qualification_agent",
            tier=ModelTier.REASONING,
            tools=[GetLeadTool, GetLeadActivitiesTool, GetBusinessConfigurationTool],
            skills=["lead-qualification", "conversation-analysis"],
        )

    @agent
    def scoring_agent(self) -> Agent:
        return self.make_agent(
            "scoring_agent",
            tier=ModelTier.REASONING,
            tools=[GetLeadActivitiesTool],
            skills=["lead-scoring", "objection-handling"],
        )

    @agent
    def next_action_agent(self) -> Agent:
        return self.make_agent(
            "next_action_agent",
            tier=ModelTier.REASONING,
            tools=[GetLeadActivitiesTool, GetBusinessConfigurationTool],
            skills=["sales-reasoning", "objection-handling"],
        )

    @task
    def qualify_lead_task(self) -> Task:
        return self.make_task("qualify_lead_task", QualificationResult, [qualification_guardrail])

    @task
    def score_lead_task(self) -> Task:
        return self.make_task("score_lead_task", AIScoreResult, [scoring_guardrail])

    @task
    def recommend_next_action_task(self) -> Task:
        return self.make_task(
            "recommend_next_action_task", NextActionRecommendation, [make_action_guardrail(self.business)]
        )

    @crew
    def crew(self) -> Crew:
        return self.sequential_crew()

    def analyze(self, lead: LeadSnapshot, activities: Sequence[ActivitySnapshot] = ()) -> LeadIntelligenceResult:
        logger.info("lead_intelligence_started", extra={"business_id": self.business.id, "lead_id": lead.id})
        output = self.kickoff(self.crew(), {
            "lead_json": lead.to_prompt_json(),
            "activities": render_activities(list(activities)),
        })
        result = LeadIntelligenceResult(
            qualification=task_result(output, QualificationResult),
            ai_score=task_result(output, AIScoreResult),
            recommendation=task_result(output, NextActionRecommendation),
            usage=output.token_usage,
        )
        logger.info(
            "lead_intelligence_finished",
            extra={"lead_id": lead.id, "token_usage": output.token_usage.model_dump()},
        )
        return result

from collections.abc import Sequence

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from pydantic import BaseModel

from ai.crews.base import ContextualCrew, task_result
from ai.guardrails import make_action_guardrail, qualification_guardrail, scoring_guardrail
from ai.schemas import (
    ActivitySnapshot,
    AIScoreResult,
    LeadSnapshot,
    NextActionRecommendation,
    QualificationResult,
)
from ai.schemas.lead import render_activities


class LeadIntelligenceResult(BaseModel):
    qualification: QualificationResult
    ai_score: AIScoreResult
    recommendation: NextActionRecommendation


@CrewBase
class LeadIntelligenceCrew(ContextualCrew):
    """Qualification → AI scoring → next-action recommendation for a single lead (MAIN_PLAN §44, §64)."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def qualification_agent(self) -> Agent:
        return self.build_agent("qualification_agent")

    @agent
    def scoring_agent(self) -> Agent:
        return self.build_agent("scoring_agent")

    @agent
    def next_action_agent(self) -> Agent:
        return self.build_agent("next_action_agent")

    @task
    def qualify_lead_task(self) -> Task:
        return self.build_task("qualify_lead_task", QualificationResult, [qualification_guardrail])

    @task
    def score_lead_task(self) -> Task:
        return self.build_task("score_lead_task", AIScoreResult, [scoring_guardrail])

    @task
    def recommend_next_action_task(self) -> Task:
        return self.build_task(
            "recommend_next_action_task", NextActionRecommendation, [make_action_guardrail(self.business)]
        )

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=self.context.verbose)

    def analyze(self, lead: LeadSnapshot, activities: Sequence[ActivitySnapshot] = ()) -> LeadIntelligenceResult:
        output = self.crew().kickoff(inputs={
            **self.base_inputs(),
            "lead_json": lead.to_prompt_json(),
            "activities": render_activities(list(activities)),
        })
        return LeadIntelligenceResult(
            qualification=task_result(output, QualificationResult),
            ai_score=task_result(output, AIScoreResult),
            recommendation=task_result(output, NextActionRecommendation),
        )

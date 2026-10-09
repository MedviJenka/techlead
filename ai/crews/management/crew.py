from collections.abc import Sequence

from crewai import Agent
from crewai.project import CrewBase, agent

from ai.crews.base import BusinessCrew
from ai.guardrails import Guardrail, as_guardrail
from ai.schemas import (
    LeadSearchFilter,
    LeadSnapshot,
    ModelTier,
    PipelineMetrics,
    PipelineReview,
    SalesAssistantAnswer,
)
from ai.tools import (
    GetBusinessConfigurationTool,
    GetBusinessMetricsTool,
    GetLeadActivitiesTool,
    SearchBusinessLeadsTool,
)
from ai.tools.business_reader import summarize_leads


def known_leads_guardrail[M: (SalesAssistantAnswer, PipelineReview)](
    model: type[M], leads: Sequence[LeadSnapshot]
) -> Guardrail:
    """Reject answers that mention lead ids the agent was not given (hallucinated leads)."""
    known = {lead.id for lead in leads}

    def validate(result: M) -> list[str]:
        items = result.highlighted_leads if isinstance(result, SalesAssistantAnswer) else result.attention_items
        unknown = sorted({item.lead_id for item in items} - known)
        return [f"These lead ids are not in the provided data: {unknown}. Use only the given leads."] if unknown else []

    return as_guardrail(model, validate)


@CrewBase
class ManagementCrew(BusinessCrew):
    """Cross-lead reasoning for the AI sales assistant and daily pipeline review (MAIN_PLAN §24-25, §44).

    The crew never queries data on its own initiative: SalesAssistantFlow (flow.py) turns the question
    into a filter, runs the tenant-scoped search, then asks for an explanation.
    """

    @agent
    def business_query_agent(self) -> Agent:
        return self.make_agent(
            "business_query_agent",
            tier=ModelTier.FAST,
            tools=[GetBusinessConfigurationTool],
            business_context=False,
        )

    @agent
    def sales_manager_agent(self) -> Agent:
        return self.make_agent(
            "sales_manager_agent",
            tier=ModelTier.REASONING,
            tools=[SearchBusinessLeadsTool, GetLeadActivitiesTool, GetBusinessMetricsTool],
            skills=["sales-reasoning", "churn-risk"],
        )

    def interpret_question(self, question: str) -> LeadSearchFilter:
        return self.run_step(
            self.business_query_agent(), "interpret_question_task", LeadSearchFilter, {"question": question}
        )

    def explain_results(
        self, question: str, search: LeadSearchFilter, leads: Sequence[LeadSnapshot]
    ) -> SalesAssistantAnswer:
        inputs = {
            "question": question,
            "search_filter": search.model_dump_json(exclude_defaults=True),
            "leads_json": summarize_leads(list(leads)) if leads else "[]",
        }
        guardrail = known_leads_guardrail(SalesAssistantAnswer, leads)
        return self.run_step(
            self.sales_manager_agent(), "explain_results_task", SalesAssistantAnswer, inputs, [guardrail]
        )

    def review_pipeline(self, metrics: PipelineMetrics, attention_leads: Sequence[LeadSnapshot]) -> PipelineReview:
        inputs = {
            "metrics_json": metrics.model_dump_json(indent=1),
            "leads_json": summarize_leads(list(attention_leads)) if attention_leads else "[]",
        }
        guardrail = known_leads_guardrail(PipelineReview, attention_leads)
        return self.run_step(self.sales_manager_agent(), "review_pipeline_task", PipelineReview, inputs, [guardrail])

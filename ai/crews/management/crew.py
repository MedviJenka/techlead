from collections.abc import Sequence

from crewai import Agent
from crewai.project import CrewBase, agent

from ai.crews.base import ContextualCrew, task_result
from ai.guardrails import Guardrail, as_guardrail
from ai.schemas import (
    LeadSearchFilter,
    LeadSnapshot,
    PipelineMetrics,
    PipelineReview,
    SalesAssistantAnswer,
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
class ManagementCrew(ContextualCrew):
    """Cross-lead reasoning for the AI sales assistant and daily pipeline review (MAIN_PLAN §24-25, §44).

    The crew never queries data on its own initiative: the Flow turns the question into a filter
    (interpret_question), runs the tenant-scoped search, then asks for an explanation.
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def business_query_agent(self) -> Agent:
        return self.build_agent("business_query_agent")

    @agent
    def sales_manager_agent(self) -> Agent:
        return self.build_agent("sales_manager_agent")

    def interpret_question(self, question: str) -> LeadSearchFilter:
        task = self.build_task("interpret_question_task", LeadSearchFilter)
        output = self.run([self.business_query_agent()], [task], {"question": question})
        return task_result(output, LeadSearchFilter)

    def explain_results(
        self, question: str, search: LeadSearchFilter, leads: Sequence[LeadSnapshot]
    ) -> SalesAssistantAnswer:
        guardrail = known_leads_guardrail(SalesAssistantAnswer, leads)
        task = self.build_task("explain_results_task", SalesAssistantAnswer, [guardrail])
        output = self.run([self.sales_manager_agent()], [task], {
            "question": question,
            "search_filter": search.model_dump_json(exclude_defaults=True),
            "leads_json": summarize_leads(list(leads)) if leads else "[]",
        })
        return task_result(output, SalesAssistantAnswer)

    def review_pipeline(self, metrics: PipelineMetrics, attention_leads: Sequence[LeadSnapshot]) -> PipelineReview:
        guardrail = known_leads_guardrail(PipelineReview, attention_leads)
        task = self.build_task("review_pipeline_task", PipelineReview, [guardrail])
        output = self.run([self.sales_manager_agent()], [task], {
            "metrics_json": metrics.model_dump_json(indent=1),
            "leads_json": summarize_leads(list(attention_leads)) if attention_leads else "[]",
        })
        return task_result(output, PipelineReview)

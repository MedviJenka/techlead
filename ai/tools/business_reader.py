import json

from pydantic import BaseModel

from ai.ports import NotFoundError
from ai.schemas import LeadSearchFilter, LeadSnapshot
from ai.tools.base import BusinessScopedTool, NoArguments

# Decision-relevant subset returned for multi-lead results; keeps prompts small (MAIN_PLAN §25).
LEAD_SUMMARY_FIELDS: frozenset[str] = frozenset({
    "id", "first_name", "last_name", "company_name", "source", "status", "priority", "lead_score",
    "budget", "currency", "timeframe", "last_contact_at", "contact_attempts", "replied", "notes",
})


def summarize_leads(leads: list[LeadSnapshot]) -> str:
    rows = [lead.model_dump(mode="json", include=set(LEAD_SUMMARY_FIELDS), exclude_none=True) for lead in leads]
    return json.dumps(rows, ensure_ascii=False, indent=1)


class GetBusinessConfigurationTool(BusinessScopedTool):
    name: str = "get_business_configuration"
    description: str = "Read the current business's AI rules: allowed actions, approval rules, tone and instructions."
    args_schema: type[BaseModel] = NoArguments

    def _run(self) -> str:
        try:
            return self._service.get_business(self.business_id).render_rules()
        except NotFoundError as error:
            return self.not_found(error)


class SearchBusinessLeadsTool(BusinessScopedTool):
    name: str = "search_business_leads"
    description: str = (
        "Search leads of the current business with structured filters (status, priority, score, budget, "
        "days since last contact, free text). Returns at most 50 compact lead summaries. Read-only."
    )
    args_schema: type[BaseModel] = LeadSearchFilter

    def _run(self, **filters: object) -> str:
        search = LeadSearchFilter.model_validate(filters)
        leads = self._service.search_leads(self.business_id, search)
        return summarize_leads(leads) if leads else "No leads match these filters."


class GetBusinessMetricsTool(BusinessScopedTool):
    name: str = "get_business_metrics"
    description: str = "Read aggregated pipeline metrics for the current business (counts, averages, stale leads)."
    args_schema: type[BaseModel] = NoArguments

    def _run(self) -> str:
        try:
            return self._service.get_pipeline_metrics(self.business_id).model_dump_json(indent=1)
        except NotFoundError as error:
            return self.not_found(error)

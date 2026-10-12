"""
The `ai.ports.LeadReadService` the crew's tools read during one analysis.

The AI protocol is synchronous and the app's database client is async, so the service reads from snapshots loaded
before the crew starts. It holds one business and one lead: an agent cannot reach any other tenant or lead.
"""

from ai.ports import NotFoundError
from ai.schemas import ActivitySnapshot, BusinessProfile, LeadSearchFilter, LeadSnapshot, PipelineMetrics


class SingleLeadReadService:

    def __init__(self, business: BusinessProfile, lead: LeadSnapshot, activities: list[ActivitySnapshot]) -> None:
        self._business = business
        self._lead = lead
        self._activities = sorted(activities, key=lambda activity: activity.created_at)

    def get_business(self, business_id: str) -> BusinessProfile:
        if business_id != self._business.id:
            raise NotFoundError(f"Business {business_id} not found")
        return self._business

    def get_lead(self, business_id: str, lead_id: str) -> LeadSnapshot:
        self.get_business(business_id)
        if lead_id != self._lead.id:
            raise NotFoundError(f"Lead {lead_id} not found")
        return self._lead

    def list_activities(self, business_id: str, lead_id: str, limit: int = 20) -> list[ActivitySnapshot]:
        self.get_lead(business_id, lead_id)
        return self._activities[-limit:]

    def search_leads(self, business_id: str, search: LeadSearchFilter) -> list[LeadSnapshot]:
        raise NotImplementedError("lead search is not available during a single-lead analysis")

    def get_pipeline_metrics(self, business_id: str) -> PipelineMetrics:
        raise NotImplementedError("pipeline metrics are not available during a single-lead analysis")

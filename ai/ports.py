"""Boundary between the AI layer and the application.

CrewAI tools only talk to the application through this read-only protocol. Every call is
business-scoped; implementations must enforce tenant isolation. Writes never go through here.
"""

from typing import Protocol

from ai.schemas import (
    ActivitySnapshot,
    BusinessProfile,
    LeadSearchFilter,
    LeadSnapshot,
    PipelineMetrics,
)


class NotFoundError(LookupError):
    """Entity does not exist within the requested business."""


class LeadReadService(Protocol):
    def get_business(self, business_id: str) -> BusinessProfile: ...

    def get_lead(self, business_id: str, lead_id: str) -> LeadSnapshot: ...

    def list_activities(self, business_id: str, lead_id: str, limit: int = 20) -> list[ActivitySnapshot]: ...

    def search_leads(self, business_id: str, search: LeadSearchFilter) -> list[LeadSnapshot]: ...

    def get_pipeline_metrics(self, business_id: str) -> PipelineMetrics: ...

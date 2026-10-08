from pydantic import BaseModel, Field
from ai.ports import NotFoundError
from ai.schemas.lead import render_activities
from ai.tools.base import BusinessScopedTool


class LeadIdInput(BaseModel):
    lead_id: str = Field(description="The lead id, e.g. 'lead_008'")


class LeadActivitiesInput(LeadIdInput):
    limit: int = Field(default=20, ge=1, le=50, description="Maximum number of most recent activities")


class GetLeadTool(BusinessScopedTool):

    name: str = "get_lead"
    description: str = "Read the normalized record of one lead in the current business. Read-only."
    args_schema: type[BaseModel] = LeadIdInput

    def _run(self, **kwargs) -> str:
        try:
            return self._service.get_lead(self.business_id, kwargs['lead_id']).to_prompt_json()
        except NotFoundError as error:
            return self.not_found(error)


class GetLeadActivitiesTool(BusinessScopedTool):
    name: str = "get_lead_activities"
    description: str = "Read the activity history (messages, calls, status changes) of one lead, oldest first. Read-only."
    args_schema: type[BaseModel] = LeadActivitiesInput

    def _run(self, lead_id: str, limit: int = 20) -> str:
        try:
            return render_activities(self._service.list_activities(self.business_id, lead_id, limit))
        except NotFoundError as error:
            return self.not_found(error)

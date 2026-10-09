from typing import Any

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel, Field

from ai.crews.management.crew import ManagementCrew
from ai.schemas import LeadSearchFilter, LeadSnapshot, SalesAssistantAnswer


class SalesAssistantState(BaseModel):
    question: str = ""
    search: LeadSearchFilter | None = None
    leads: list[LeadSnapshot] = Field(default_factory=list)


class SalesAssistantFlow(Flow[SalesAssistantState]):
    """Question → search filter (agent) → tenant-scoped search (application) → grounded answer (agent).

    The agent never runs the query: the application does, with the business id fixed by the crew.
    """

    def __init__(self, crew: ManagementCrew, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.crew = crew

    @start()
    def interpret(self) -> None:
        self.state.search = self.crew.interpret_question(self.state.question)

    @listen(interpret)
    def search_leads(self) -> None:
        assert self.state.search is not None
        self.state.leads = self.crew.runtime.service.search_leads(self.crew.business.id, self.state.search)

    @listen(search_leads)
    def explain(self) -> SalesAssistantAnswer:
        assert self.state.search is not None
        return self.crew.explain_results(self.state.question, self.state.search, self.state.leads)

    def ask(self, question: str) -> SalesAssistantAnswer:
        result = self.kickoff(inputs={"question": question})
        assert isinstance(result, SalesAssistantAnswer)
        return result

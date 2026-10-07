from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from crewai import Agent, Crew, CrewOutput, Process, Task
from crewai.llms.base_llm import BaseLLM
from crewai.skills.models import Skill
from crewai.tools import BaseTool
from pydantic import BaseModel
from ai.guardrails import Guardrail
from ai.schemas import BusinessProfile


class CrewExecutionError(RuntimeError):
    """A crew finished without a valid structured result."""


@dataclass(frozen=True)
class AgentResources:
    llm: BaseLLM | str
    tools: Sequence[BaseTool]
    skills: Sequence[Skill]


@dataclass(frozen=True)
class CrewContext:
    """Everything a crew needs for one business. Built by BusinessCrewFactory."""

    business: BusinessProfile
    agents: Mapping[str, AgentResources]
    verbose: bool = False
    guardrail_max_retries: int = 2
    max_agent_iterations: int = 8


class ContextualCrew:
    """Shared plumbing for @CrewBase crews whose agents are configured per business.

    Agents and tasks keep their prompts in YAML; LLM, tools, skills and guardrails are injected
    from the CrewContext so agent code is never duplicated per customer.
    """

    agents_config: dict[str, Any]
    tasks_config: dict[str, Any]

    def __init__(self, context: CrewContext) -> None:
        self.context = context

    @property
    def business(self) -> BusinessProfile:
        return self.context.business

    def build_agent(self, name: str) -> Agent:
        resources = self.context.agents[name]
        return Agent(
            config=self.agents_config[name],
            llm=resources.llm,
            tools=list(resources.tools),
            skills=list(resources.skills) or None,
            allow_delegation=False,
            max_iter=self.context.max_agent_iterations,
            verbose=self.context.verbose,
        )

    def build_task(self, name: str, output: type[BaseModel], guardrails: Sequence[Guardrail] = ()) -> Task:
        return Task(
            name=name,
            config=self.tasks_config[name],
            output_pydantic=output,
            guardrails=list(guardrails) or None,
            guardrail_max_retries=self.context.guardrail_max_retries,
        )

    def run(self, agents: Sequence[Agent], tasks: Sequence[Task], inputs: Mapping[str, Any]) -> CrewOutput:
        crew = Crew(
            agents=list(agents),
            tasks=list(tasks),
            process=Process.sequential,
            verbose=self.context.verbose,
        )
        return crew.kickoff(inputs={**self.base_inputs(), **inputs})

    def base_inputs(self) -> dict[str, str]:
        return {
            "business_name": self.business.name,
            "industry": self.business.industry or "unspecified",
            "business_rules": self.business.render_rules(),
            "now": datetime.now(UTC).isoformat(timespec="minutes"),
        }


def task_result[M: BaseModel](output: CrewOutput, model: type[M]) -> M:
    """Pick the structured output of the given type from a crew run."""
    for task_output in output.tasks_output:
        if isinstance(task_output.pydantic, model):
            return task_output.pydantic
    raise CrewExecutionError(f"Crew produced no {model.__name__}")

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self
from crewai import Agent, Crew, CrewOutput, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from pydantic import BaseModel
from ai.config import LLMResolver, LLMSettings
from ai.guardrails import Guardrail
from ai.ports import LeadReadService
from ai.schemas import BusinessProfile, ModelTier
from ai.skill_library import SkillLibrary
from ai.tools import BusinessScopedTool


logger = logging.getLogger(__name__)


class CrewExecutionError(RuntimeError):
    """A crew finished without a valid structured result."""


@dataclass(frozen=True)
class AIRuntime:
    """What every crew needs regardless of business: read access, model tiers and the skill library."""

    service: LeadReadService
    llm: LLMResolver
    skills: SkillLibrary
    verbose: bool = False
    guardrail_max_retries: int = 2
    max_agent_iterations: int = 8

    @classmethod
    def from_env(cls, service: LeadReadService, skills: SkillLibrary | None = None) -> "AIRuntime":
        from settings import get_config  # lazy: importing ai.* must not require a configured environment

        return cls(service, LLMSettings.from_env().resolver(), skills or SkillLibrary(), verbose=get_config().VERBOSE)


class BusinessCrew:
    """
    Base for @CrewBase crews. Prompts live in YAML; each @agent method declares its own model tier,
    tools and skills (least privilege, MAIN_PLAN §43), so one crew file shows everything its agents can do.

    Fixed pipelines use @task/@crew. Single steps that a Flow orchestrates use ``run_step``, which
    builds the task per call so per-call guardrails never leak between runs.
    """

    agents: list[BaseAgent]
    tasks: list[Task]
    agents_config: Any = "config/agents.yaml"
    tasks_config: Any = "config/tasks.yaml"

    def __init__(self, business: BusinessProfile, runtime: AIRuntime) -> None:
        self.business = business
        self.runtime = runtime

    @classmethod
    def for_business(cls, runtime: AIRuntime, business_id: str) -> Self:
        return cls(runtime.service.get_business(business_id), runtime)

    def make_agent(
        self,
        name: str,
        *,
        tier: ModelTier,
        tools: Sequence[type[BusinessScopedTool]] = (),
        skills: Sequence[str] = (),
        business_context: bool = True,
    ) -> Agent:
        """``business_context`` also attaches the industry and business-specific skills."""
        composed = self.runtime.skills.compose(skills, self.business, business_context=business_context)
        return Agent(
            config=self.agents_config[name],
            llm=self.runtime.llm(tier),
            tools=[tool.bind(self.runtime.service, self.business.id) for tool in tools],
            skills=composed or None,
            allow_delegation=False,
            max_iter=self.runtime.max_agent_iterations,
            verbose=self.runtime.verbose,
        )

    def make_task(self, name: str, output: type[BaseModel], guardrails: Sequence[Guardrail] = ()) -> Task:
        return Task(
            name=name,
            config=self.tasks_config[name],
            output_pydantic=output,
            guardrails=list(guardrails) or None,
            guardrail_max_retries=self.runtime.guardrail_max_retries,
        )

    def sequential_crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=self.runtime.verbose)

    def kickoff(self, crew: Crew, inputs: Mapping[str, Any]) -> CrewOutput:
        logger.info("crew_run", extra={"business_id": self.business.id, "tasks": [task.name for task in crew.tasks]})
        return crew.kickoff(inputs={**self.base_inputs(), **inputs})

    def run_step[M: BaseModel](
        self,
        agent: Agent,
        task_name: str,
        output: type[M],
        inputs: Mapping[str, Any],
        guardrails: Sequence[Guardrail] = (),
    ) -> M:
        """Run one agent on one task, built for this call, and return its structured output."""
        task = self.make_task(task_name, output, guardrails)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=self.runtime.verbose)
        return task_result(self.kickoff(crew, inputs), output)

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
    logger.error("crew_output_missing", extra={"model": model.__name__})
    raise CrewExecutionError(f"Crew produced no {model.__name__}")

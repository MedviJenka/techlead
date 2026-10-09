import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, Self

from crewai import Agent, Crew, CrewOutput, Memory, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project.utils import cache as memo_cache
from pydantic import BaseModel

from ai.config import LLMResolver, LLMSettings
from ai.guardrails import Guardrail
from ai.memory import AgentMemoryStore, MemoryKey
from ai.ports import LeadReadService
from ai.schemas import BusinessProfile, ModelTier
from ai.tools import BusinessScopedTool
from app.core.logger import Logger

logger = Logger(__name__)


class CrewExecutionError(RuntimeError):
    """A crew finished without a valid structured result."""


@dataclass(frozen=True)
class AIRuntime:
    """What every crew needs regardless of business: read access and model tiers.

    ``memory`` gives each agent its own memory per business; None (tests, evals) runs agents without one.
    """

    service: LeadReadService
    llm: LLMResolver
    verbose: bool = False
    guardrail_max_retries: int = 2
    max_agent_iterations: int = 8
    memory: AgentMemoryStore | None = None

    @classmethod
    def from_env(cls, service: LeadReadService) -> "AIRuntime":
        from settings import get_config  # lazy: importing ai.* must not require a configured environment

        return cls(
            service,
            LLMSettings.from_env().resolver(),
            verbose=get_config().VERBOSE,
            memory=_memory_store(),
        )


class BusinessCrew:
    """
    Base for @CrewBase crews. Prompts live in YAML and skills in the crew's ``skills/`` folder; each @agent
    method declares its own model tier and tools (least privilege, MAIN_PLAN §43).

    Fixed pipelines use @task/@crew. Single steps that a Flow orchestrates use ``run_step``, which
    builds the task per call so per-call guardrails never leak between runs.
    """

    agents: list[BaseAgent]
    tasks: list[Task]
    agents_config: Any = "config/agents.yaml"
    tasks_config: Any = "config/tasks.yaml"
    base_directory: Path  # the crew's folder, set by @CrewBase

    def __init__(self, business: BusinessProfile, runtime: AIRuntime) -> None:
        self.business = business
        self.runtime = runtime
        self._memory_keys: set[MemoryKey] = set()
        weakref.finalize(self, _forget_memoized, id(self))

    @classmethod
    def for_business(cls, runtime: AIRuntime, business_id: str) -> Self:
        return cls(runtime.service.get_business(business_id), runtime)

    def make_agent(
        self,
        name: str,
        *,
        tier: ModelTier,
        tools: Sequence[type[BusinessScopedTool]] = (),
        memory: bool = True,
    ) -> Agent:
        """``memory`` gives the agent its own memory for this business when the runtime has a memory store."""
        return Agent(
            config=self.agents_config[name],
            llm=self.runtime.llm(tier),
            tools=[tool.bind(self.runtime.service, self.business.id) for tool in tools],
            skills=[self.base_directory / "skills"],
            allow_delegation=False,
            max_iter=self.runtime.max_agent_iterations,
            verbose=self.runtime.verbose,
            memory=self.agent_memory(name) if memory else None,
        )

    def agent_memory(self, name: str) -> Memory | None:
        store = self.runtime.memory
        if store is None:
            return None
        key = MemoryKey(self.business.id, type(self).__name__, name)
        self._memory_keys.add(key)
        return store.memory(key, self.runtime.llm(ModelTier.FAST))

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
        logger.fire("crew_run", business_id=self.business.id, tasks=[task.name for task in crew.tasks])
        try:
            return crew.kickoff(inputs={**self.base_inputs(), **inputs})
        finally:
            self.sync_memory()

    def sync_memory(self) -> None:
        """Upload what the agents remembered. A failed upload is logged, never fails the run: the next sync retries."""
        store = self.runtime.memory
        if store is None:
            return
        for key in self._memory_keys:
            try:
                store.sync(key)
            except Exception as exc:
                logger.fire("agent_memory_sync_failed", level="error", prefix=key.prefix, _exc_info=exc)

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
    logger.fire("crew_output_missing", level="error", model=model.__name__)
    raise CrewExecutionError(f"Crew produced no {model.__name__}")


def _forget_memoized(crew_id: int) -> None:
    """Drop a released crew's @agent/@task results from CrewAI's process-wide memo cache.

    CrewAI keys that cache by the crew's id(). Without this, the next crew allocated at the same address (any
    business, in the long-running worker) would get the old crew's agents with their tools and memory, and the
    cache would grow with every crew built.
    """
    marker = f"('__instance__', {crew_id})"
    with memo_cache._lock.w_locked():
        for key in [key for key in memo_cache._cache if marker in key]:
            del memo_cache._cache[key]


@cache
def _memory_store() -> AgentMemoryStore | None:
    """One store per process (it tracks what is already in the bucket); None when AI_MEMORY_BUCKET is unset."""
    from ai.memory import S3ObjectStore
    from settings import get_config

    config = get_config()
    objects = S3ObjectStore.from_settings(config)
    return AgentMemoryStore(objects, config.AI_MEMORY_CACHE_DIR) if objects else None

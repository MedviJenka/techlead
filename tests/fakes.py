"""Deterministic stand-in for an LLM so crews can run end-to-end in tests without a provider."""

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from typing import Any

from crewai.llms.base_llm import BaseLLM
from pydantic import BaseModel, PrivateAttr


class ScriptedLLM(BaseLLM):
    """Answers each task with the next scripted payload queued for that task name."""

    _script: dict[str, deque[str]] = PrivateAttr(default_factory=lambda: defaultdict(deque))
    _calls: list[str] = PrivateAttr(default_factory=list)

    def __init__(self, script: Mapping[str, Sequence[BaseModel | str]], **kwargs: Any) -> None:
        super().__init__(model="scripted-test-llm", **kwargs)
        for task_name, answers in script.items():
            self._script[task_name].extend(a if isinstance(a, str) else a.model_dump_json() for a in answers)

    @property
    def calls(self) -> list[str]:
        return list(self._calls)

    def call(self, messages: Any, tools: Any = None, callbacks: Any = None, available_functions: Any = None,
             from_task: Any = None, from_agent: Any = None, response_model: Any = None) -> str:
        name = getattr(from_task, "name", None) or "unknown"
        self._calls.append(name)
        queue = self._script.get(name)
        if not queue:
            raise AssertionError(f"Unexpected LLM call for task {name!r}")
        answer = queue.popleft() if len(queue) > 1 else queue[0]
        return f"Thought: I now know the final answer\nFinal Answer: {answer}"

    async def acall(self, *args: Any, **kwargs: Any) -> str:
        return self.call(*args, **kwargs)

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 128_000

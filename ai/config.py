from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from crewai import LLM
from crewai.llms.base_llm import BaseLLM
from ai.schemas import ModelTier
type LLMResolver = Callable[[ModelTier], BaseLLM]


@dataclass(frozen=True)
class LLMSettings:
    """Provider-agnostic model selection. Any LiteLLM/CrewAI model id works ('openai/gpt-4o', 'anthropic/...')."""

    reasoning_model: str
    fast_model: str
    temperature: float | None = None  # None: the provider's default (reasoning models accept no other)
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "LLMSettings":
        from settings import get_config  # lazy: importing ai.* must not require a configured environment

        config = get_config()
        return cls(
            reasoning_model=config.AI_REASONING_MODEL or config.OPENAI_MODEL,
            fast_model=config.AI_FAST_MODEL or config.OPENAI_MODEL,
            temperature=config.AI_TEMPERATURE,
        )

    def resolver(self) -> LLMResolver:
        @cache
        def resolve(tier: ModelTier) -> BaseLLM:
            model = self.reasoning_model if tier == ModelTier.REASONING else self.fast_model
            return LLM(model=model, temperature=self.temperature, timeout=self.timeout_seconds)

        return resolve

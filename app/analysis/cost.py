"""What one AI run cost (MAIN_PLAN §65: cost per lead is recorded). Token counts always; dollars when priced."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.schemas.analysis import RunCost
from settings import Settings

_MILLION = Decimal(1_000_000)
_MICRODOLLAR = Decimal("0.000001")


class TokenUsage(Protocol):
    """Token counts of a run (CrewAI's ``UsageMetrics``)."""

    prompt_tokens: int
    cached_prompt_tokens: int
    completion_tokens: int
    successful_requests: int


@dataclass(frozen=True)
class TokenPrices:
    """USD per million tokens. Cached prompt tokens cost ``cached_input`` when set, else the full input price."""

    input: Decimal
    output: Decimal
    cached_input: Decimal | None = None

    @classmethod
    def from_settings(cls, config: Settings) -> "TokenPrices | None":
        if config.AI_PRICE_INPUT_PER_MTOK is None or config.AI_PRICE_OUTPUT_PER_MTOK is None:
            return None
        cached = config.AI_PRICE_CACHED_INPUT_PER_MTOK
        return cls(
            Decimal(str(config.AI_PRICE_INPUT_PER_MTOK)),
            Decimal(str(config.AI_PRICE_OUTPUT_PER_MTOK)),
            None if cached is None else Decimal(str(cached)),
        )

    def cost(self, usage: TokenUsage) -> Decimal:
        cached = min(usage.cached_prompt_tokens, usage.prompt_tokens)
        cached_price = self.input if self.cached_input is None else self.cached_input
        total = (
            (usage.prompt_tokens - cached) * self.input
            + cached * cached_price
            + usage.completion_tokens * self.output
        ) / _MILLION
        return total.quantize(_MICRODOLLAR)


def run_cost(model: str, usage: TokenUsage | None, prices: TokenPrices | None) -> RunCost | None:
    """None when the run reported no usage (e.g. a scripted LLM in tests)."""
    if usage is None:
        return None
    return RunCost(
        model=model,
        prompt_tokens=usage.prompt_tokens,
        cached_prompt_tokens=usage.cached_prompt_tokens,
        completion_tokens=usage.completion_tokens,
        requests=usage.successful_requests,
        cost_usd=prices.cost(usage) if prices else None,
    )

"""Runs the evaluation cases through LeadIntelligenceCrew and checks each answer."""

import time
from collections.abc import Callable, Iterable, Mapping

from crewai.types.usage_metrics import UsageMetrics
from pydantic import BaseModel, Field, computed_field

from ai.crews.lead_intelligence.crew import LeadIntelligenceCrew, LeadIntelligenceResult
from ai.data.sample_store import InMemoryLeadStore
from ai.evals.cases import RANKING, EvalCase
from ai.schemas import Priority
from app.core.logger import Logger

logger = Logger("evals")


class CaseResult(BaseModel):
    lead_id: str
    failures: list[str] = Field(default_factory=list)
    error: str | None = None
    elapsed_s: float = 0.0
    result: LeadIntelligenceResult | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        return self.error is None and not self.failures


class EvalReport(BaseModel):
    model: str
    cases: list[CaseResult]
    ranking_failures: list[str] = Field(default_factory=list)
    min_pass_rate: float

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pass_rate(self) -> float:
        return sum(case.passed for case in self.cases) / len(self.cases) if self.cases else 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        return bool(self.cases) and self.pass_rate >= self.min_pass_rate and not self.ranking_failures

    @computed_field  # type: ignore[prop-decorator]
    @property
    def usage(self) -> UsageMetrics:
        total = UsageMetrics()
        for case in self.cases:
            if case.result is not None and case.result.usage is not None:
                total.add_usage_metrics(case.result.usage)
        return total

    def render(self) -> str:
        lines = [f"LeadIntelligenceCrew evaluation, model {self.model}", ""]
        for case in self.cases:
            summary = ""
            if case.result is not None:
                r = case.result
                summary = (
                    f"qualified={r.qualification.qualified} score={r.ai_score.overall_ai_score} "
                    f"action={r.recommendation.action.value} priority={r.recommendation.priority.value}"
                )
            lines.append(f"{'PASS' if case.passed else 'FAIL'}  {case.lead_id}  {case.elapsed_s:6.1f}s  {summary}")
            problems = [*case.failures, *([case.error] if case.error else [])]
            lines.extend(f"        - {problem}" for problem in problems)
        lines.append("")
        lines.extend(f"RANKING FAIL  {problem}" for problem in self.ranking_failures)
        passed = sum(case.passed for case in self.cases)
        lines.append(f"Cases passed: {passed}/{len(self.cases)} ({self.pass_rate:.0%}, need {self.min_pass_rate:.0%})")
        usage = self.usage
        per_lead = usage.total_tokens // len(self.cases) if self.cases else 0
        lines.append(
            f"Tokens: {usage.total_tokens} total ({usage.prompt_tokens} prompt, "
            f"{usage.completion_tokens} completion), ~{per_lead} per lead, "
            f"{usage.successful_requests} LLM requests"
        )
        lines.append(f"Result: {'PASS' if self.passed else 'FAIL'}")
        return "\n".join(lines)


def check_case(case: EvalCase, result: LeadIntelligenceResult) -> list[str]:
    """What is wrong with one answer, compared with the case's expectations. Empty means it passed."""
    failures: list[str] = []
    qualification, score, rec = result.qualification, result.ai_score.overall_ai_score, result.recommendation
    if case.qualified is not None and qualification.qualified != case.qualified:
        failures.append(f"qualified={qualification.qualified}, expected {case.qualified}")
    if not case.min_score <= score <= case.max_score:
        failures.append(f"overall_ai_score={score}, expected {case.min_score}-{case.max_score}")
    if case.actions is not None and rec.action not in case.actions:
        expected = ", ".join(sorted(action.value for action in case.actions))
        failures.append(f"action={rec.action.value}, expected one of: {expected}")
    order = list(Priority)  # declared from LOW to CRITICAL
    if not order.index(case.min_priority) <= order.index(rec.priority) <= order.index(case.max_priority):
        failures.append(f"priority={rec.priority.value}, expected {case.min_priority.value}-{case.max_priority.value}")
    return failures


def check_ranking(scores: Mapping[str, int]) -> list[str]:
    """Every scored lead in the higher group must outscore every scored lead in the lower group."""
    higher, lower = RANKING
    return [
        f"{hot} scored {scores[hot]}, not above {cold} ({scores[cold]})"
        for hot in sorted(higher & scores.keys())
        for cold in sorted(lower & scores.keys())
        if scores[hot] <= scores[cold]
    ]


def run_lead_intelligence_eval(
    store: InMemoryLeadStore,
    make_crew: Callable[[], LeadIntelligenceCrew],
    business_id: str,
    cases: Iterable[EvalCase],
    *,
    model: str,
    min_pass_rate: float,
) -> EvalReport:
    """Run every case one after the other. A failed run is recorded and the evaluation goes on.

    Each case gets a new crew with new LLM objects: CrewAI reports an LLM object's running token total,
    and a shared one would add every earlier case to each case's usage.
    """
    results: list[CaseResult] = []
    for case in cases:
        crew = make_crew()
        lead = store.get_lead(business_id, case.lead_id)
        started = time.perf_counter()
        try:
            result = crew.analyze(lead, store.list_activities(business_id, case.lead_id))
            outcome = CaseResult(lead_id=case.lead_id, failures=check_case(case, result), result=result)
        except Exception as exc:  # timeouts, malformed output, exhausted guardrail retries: all a failed case
            logger.fire("eval_case_error", level="warning", lead_id=case.lead_id, error=repr(exc))
            outcome = CaseResult(lead_id=case.lead_id, error=f"{type(exc).__name__}: {exc}")
        outcome.elapsed_s = round(time.perf_counter() - started, 1)
        results.append(outcome)
    scores = {case.lead_id: case.result.ai_score.overall_ai_score for case in results if case.result is not None}
    return EvalReport(model=model, cases=results, ranking_failures=check_ranking(scores), min_pass_rate=min_pass_rate)

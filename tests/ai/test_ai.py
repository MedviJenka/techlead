"""ResponseEvaluatorCrew: wiring with a scripted LLM, and an opt-in live run that grades the ConversationCrew.

The live tests make real, billed LLM calls: ``RUN_LIVE_AI_EVALS=1 pytest tests/ai``.
"""

import os
from datetime import UTC, datetime

import pytest

from ai.config import LLMSettings
from ai.crews import AIRuntime, ConversationCrew
from ai.data.sample_store import InMemoryLeadStore
from ai.schemas import Channel, ConversationAnalysis, FollowupDraft, InboundMessage, LeadSnapshot
from tests.ai.crew import ResponseEvaluatorCrew
from tests.ai.schema import Anomaly, CriterionScore, ResponseEvaluation, Severity
from tests.conftest import BUSINESS_ID, NOW, make_crew
from tests.fakes import ScriptedLLM

MESSAGE = InboundMessage(channel=Channel.WHATSAPP, received_at=NOW,
                         body="Looks good. I need to check it with my partner. Call me on Sunday.")
ANALYSIS = ConversationAnalysis(
    intent="Wants a call on Sunday after checking with their partner", purchase_intent="high", sentiment="positive",
    requested_actions=["call on Sunday"], decision_dependency="partner approval",
    followup_date=datetime(2026, 10, 11, 9, 0, tzinfo=UTC),
)
DRAFT = FollowupDraft(channel=Channel.WHATSAPP, objective="Confirm the Sunday call", tone="friendly",
                      message="Hi Tomer, great to hear! Did you get a chance to go over it with your partner? "
                              "Does 10:00 or 14:00 on Sunday work for the call?")


def evaluation(score: int, *anomalies: Anomaly) -> ResponseEvaluation:
    return ResponseEvaluation(
        score=score, confidence_level=0.9, anomalies=list(anomalies), output_notice="Graded.",
        criteria=[CriterionScore(name="faithfulness", score=score // 10, comment="")],
    )


class TestResponseEvaluation:

    def test_passes_above_threshold_without_blocking_anomalies(self) -> None:
        minor = Anomaly(kind="tone", severity=Severity.LOW, evidence="great to hear!", explanation="A bit eager")
        assert evaluation(85, minor).passed()

    def test_fails_below_threshold(self) -> None:
        assert not evaluation(60).passed()
        assert evaluation(60).passed(min_score=50)

    @pytest.mark.parametrize("severity", [Severity.HIGH, Severity.CRITICAL])
    def test_blocking_anomaly_fails_a_high_score(self, severity: Severity) -> None:
        price = Anomaly(kind="hallucination", severity=severity, evidence="only 9,900 ILS",
                        explanation="No price was given")
        assert not evaluation(95, price).passed()


class TestResponseEvaluatorCrew:

    def test_evaluates_an_analysis(self, store: InMemoryLeadStore, tomer: LeadSnapshot) -> None:
        llm = ScriptedLLM({"evaluate_analysis_task": [evaluation(90)]})
        crew = make_crew(ResponseEvaluatorCrew, store, llm)

        result = crew.evaluate_analysis(tomer, MESSAGE, ANALYSIS, store.list_activities(BUSINESS_ID, tomer.id))

        assert result.score == 90
        assert llm.calls == ["evaluate_analysis_task"]

    def test_evaluates_a_followup(self, store: InMemoryLeadStore, tomer: LeadSnapshot) -> None:
        llm = ScriptedLLM({"evaluate_followup_task": [evaluation(80)]})
        crew = make_crew(ResponseEvaluatorCrew, store, llm)

        result = crew.evaluate_followup(tomer, DRAFT, ANALYSIS, store.list_activities(BUSINESS_ID, tomer.id))

        assert result.passed()
        assert llm.calls == ["evaluate_followup_task"]

    def test_judge_has_no_tools(self, store: InMemoryLeadStore) -> None:
        crew = make_crew(ResponseEvaluatorCrew, store, ScriptedLLM({}))
        assert crew.response_evaluator().tools == []


live = pytest.mark.skipif(not os.environ.get("RUN_LIVE_AI_EVALS"), reason="real, billed LLM calls")


@live
class TestConversationCrewQuality:
    """Run the real ConversationCrew on the sample lead and let the judge grade each step."""

    @pytest.fixture
    def runtime(self, store: InMemoryLeadStore) -> AIRuntime:
        return AIRuntime(store, LLMSettings.from_env().resolver())

    def test_analysis_and_followup_pass_the_judge(self, store: InMemoryLeadStore, tomer: LeadSnapshot,
                                                   runtime: AIRuntime) -> None:
        activities = store.list_activities(BUSINESS_ID, tomer.id)
        conversation = ConversationCrew.for_business(runtime, BUSINESS_ID)
        judge = ResponseEvaluatorCrew.for_business(runtime, BUSINESS_ID)

        analysis = conversation.analyze_message(tomer, MESSAGE, activities)
        analysis_grade = judge.evaluate_analysis(tomer, MESSAGE, analysis, activities)
        draft = conversation.draft_followup(tomer, Channel.WHATSAPP, insights=analysis, activities=activities)
        draft_grade = judge.evaluate_followup(tomer, draft, analysis, activities)

        assert analysis_grade.passed(), analysis_grade.model_dump_json(indent=2)
        assert draft_grade.passed(), draft_grade.model_dump_json(indent=2)

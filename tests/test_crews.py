"""End-to-end crew runs with a scripted LLM: wiring, structured outputs and guardrail retries."""

from datetime import UTC, datetime, timedelta

import pytest

from ai.crews import ConversationCrew, LeadIntelligenceCrew, ManagementCrew, SalesAssistantFlow
from ai.data.sample_store import InMemoryLeadStore
from ai.schemas import (
    AIScoreResult,
    Channel,
    ConversationAnalysis,
    FollowupDraft,
    InboundMessage,
    LeadHighlight,
    LeadSearchFilter,
    LeadSnapshot,
    NextAction,
    NextActionRecommendation,
    PipelineReview,
    Priority,
    QualificationResult,
    SalesAssistantAnswer,
)
from ai.skill_library import SkillLibrary
from tests.conftest import BUSINESS_ID, make_crew
from tests.fakes import ScriptedLLM

QUALIFIED = QualificationResult(
    qualified=True, confidence=0.92, intent="high", urgency="immediate", fit="excellent",
    positive_signals=["Timeframe: immediate", "Budget defined: 90,000 ILS", "1,200 leads/month"],
    summary="Immediate requirement, clear business need, defined budget and active engagement.",
)
AI_SCORE = AIScoreResult(intent_score=95, urgency_score=98, fit_score=94, engagement_score=88, sentiment_score=90,
                         overall_ai_score=94, reasons=["Immediate timeframe", "Defined budget", "Replied on first call"])


def call_now() -> NextActionRecommendation:
    return NextActionRecommendation(
        action=NextAction.CALL, priority=Priority.CRITICAL,
        reason="Schedule technical discovery call immediately.",
        due_at=datetime.now(UTC) + timedelta(minutes=30), requires_human_approval=False,
    )


class TestLeadIntelligenceCrew:

    def test_produces_all_structured_results(
        self, store: InMemoryLeadStore, skill_library: SkillLibrary, tomer: LeadSnapshot
    ) -> None:
        llm = ScriptedLLM({"qualify_lead_task": [QUALIFIED], "score_lead_task": [AI_SCORE],
                           "recommend_next_action_task": [call_now()]})
        crew = make_crew(LeadIntelligenceCrew, store, llm, skill_library)

        result = crew.analyze(tomer, store.list_activities(BUSINESS_ID, tomer.id))

        assert result.qualification.qualified
        assert result.ai_score.overall_ai_score == 94
        assert result.recommendation.action == NextAction.CALL
        assert llm.calls == ["qualify_lead_task", "score_lead_task", "recommend_next_action_task"]

    def test_guardrail_forces_retry_on_invalid_recommendation(
        self, store: InMemoryLeadStore, skill_library: SkillLibrary, tomer: LeadSnapshot
    ) -> None:
        unapproved_email = NextActionRecommendation(action=NextAction.SEND_EMAIL, priority=Priority.HIGH,
                                                    reason="Send details", requires_human_approval=False)
        llm = ScriptedLLM({"qualify_lead_task": [QUALIFIED], "score_lead_task": [AI_SCORE],
                           "recommend_next_action_task": [unapproved_email, call_now()]})
        crew = make_crew(LeadIntelligenceCrew, store, llm, skill_library)

        result = crew.analyze(tomer)

        assert result.recommendation.action == NextAction.CALL
        assert llm.calls.count("recommend_next_action_task") == 2

    def test_persistent_guardrail_failure_raises(
        self, store: InMemoryLeadStore, skill_library: SkillLibrary, tomer: LeadSnapshot
    ) -> None:
        inconsistent = AI_SCORE.model_copy(update={"overall_ai_score": 5})
        llm = ScriptedLLM({"qualify_lead_task": [QUALIFIED], "score_lead_task": [inconsistent]})
        crew = make_crew(LeadIntelligenceCrew, store, llm, skill_library)

        with pytest.raises(Exception, match="guardrail"):
            crew.analyze(tomer)


class TestConversationCrew:
    def test_analyze_message(self, store: InMemoryLeadStore, skill_library: SkillLibrary, tomer: LeadSnapshot) -> None:
        analysis = ConversationAnalysis(intent="Wants to discuss routing after partner review", purchase_intent="high",
                                        sentiment="positive", decision_dependency="partner approval",
                                        requested_actions=["call on Sunday"])
        llm = ScriptedLLM({"analyze_conversation_task": [analysis]})
        crew = make_crew(ConversationCrew, store, llm, skill_library)
        message = InboundMessage(channel=Channel.WHATSAPP, received_at=datetime.now(UTC),
                                 body="Looks good. I need to check it with my partner. Call me on Sunday.")

        result = crew.analyze_message(tomer, message)

        assert result.decision_dependency == "partner approval"

    def test_followup_with_invented_discount_is_retried(
        self, store: InMemoryLeadStore, skill_library: SkillLibrary, tomer: LeadSnapshot
    ) -> None:
        pushy = FollowupDraft(channel=Channel.WHATSAPP, message="Book today and get a 15% discount!",
                              objective="Close", tone="pushy")
        good = FollowupDraft(channel=Channel.WHATSAPP, objective="Confirm review", tone="warm",
                             message="Hi Tomer, did you get a chance to go over the routing plan with your partner?")
        llm = ScriptedLLM({"generate_followup_task": [pushy, good]})
        crew = make_crew(ConversationCrew, store, llm, skill_library)

        draft = crew.draft_followup(tomer, Channel.WHATSAPP, recommendation=call_now())

        assert draft == good
        assert llm.calls == ["generate_followup_task", "generate_followup_task"]


class TestManagementCrew:
    def test_question_to_filter_to_answer(self, store: InMemoryLeadStore, skill_library: SkillLibrary) -> None:
        search = LeadSearchFilter(min_score=80, not_contacted_for_days=0)
        invented = SalesAssistantAnswer(answer="Call lead_999", highlighted_leads=[
            LeadHighlight(lead_id="lead_999", name="Ghost", reason="?", suggested_action=NextAction.CALL)])
        grounded = SalesAssistantAnswer(answer="Call Tomer Katz first.", highlighted_leads=[
            LeadHighlight(lead_id="lead_008", name="Tomer Katz", reason="Immediate need", suggested_action=NextAction.CALL)])
        llm = ScriptedLLM({"interpret_question_task": [search], "explain_results_task": [invented, grounded]})
        crew = make_crew(ManagementCrew, store, llm, skill_library)

        question = "Who should I call today?"
        parsed = crew.interpret_question(question)
        leads = store.search_leads(BUSINESS_ID, parsed)  # the application runs the query, not the agent
        answer = crew.explain_results(question, parsed, leads)

        assert parsed.min_score == 80
        assert answer.highlighted_leads[0].lead_id == "lead_008"
        assert llm.calls.count("explain_results_task") == 2

    def test_pipeline_review(self, store: InMemoryLeadStore, skill_library: SkillLibrary) -> None:
        review = PipelineReview(headline="1 hot lead not contacted", priorities_today=["Call Daniel Cohen"])
        llm = ScriptedLLM({"review_pipeline_task": [review]})
        crew = make_crew(ManagementCrew, store, llm, skill_library)
        hot = store.search_leads(BUSINESS_ID, LeadSearchFilter(min_score=80))

        result = crew.review_pipeline(store.get_pipeline_metrics(BUSINESS_ID), hot)

        assert result.headline == review.headline

    def test_sales_assistant_flow_runs_the_search_itself(
        self, store: InMemoryLeadStore, skill_library: SkillLibrary
    ) -> None:
        tomer = LeadHighlight(lead_id="lead_008", name="Tomer Katz", reason="Immediate need",
                              suggested_action=NextAction.CALL)
        grounded = SalesAssistantAnswer(answer="Call Tomer Katz first.", highlighted_leads=[tomer])
        llm = ScriptedLLM({"interpret_question_task": [LeadSearchFilter(min_score=80)],
                           "explain_results_task": [grounded]})
        flow = SalesAssistantFlow(make_crew(ManagementCrew, store, llm, skill_library))

        answer = flow.ask("Who should I call today?")

        assert answer == grounded
        assert flow.state.leads and all(lead.lead_score >= 80 for lead in flow.state.leads)
        assert llm.calls == ["interpret_question_task", "explain_results_task"]

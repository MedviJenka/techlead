from datetime import UTC, datetime, timedelta

from crewai import TaskOutput

from ai.guardrails import (
    make_action_validator,
    make_messaging_validator,
    qualification_guardrail,
    validate_ai_score,
    validate_qualification,
)
from ai.schemas import (
    AIConfiguration,
    AIScoreResult,
    AutonomyLevel,
    BusinessProfile,
    Channel,
    FollowupDraft,
    LeadSnapshot,
    NextAction,
    NextActionRecommendation,
    Priority,
    QualificationResult,
)
from tests.conftest import NOW


def qualification(**overrides: object) -> QualificationResult:
    base = {"qualified": True, "confidence": 0.8, "intent": "high", "urgency": "high", "fit": "good",
                "positive_signals": ["Budget defined"], "summary": "Clear need, defined budget and short timeframe."}
    return QualificationResult.model_validate({**base, **overrides})


def score(**overrides: object) -> AIScoreResult:
    base = {"intent_score": 80, "urgency_score": 80, "fit_score": 80, "engagement_score": 80, "sentiment_score": 80,
                "overall_ai_score": 80, "reasons": ["a", "b"]}
    return AIScoreResult.model_validate({**base, **overrides})


def recommendation(**overrides: object) -> NextActionRecommendation:
    base = {"action": "call", "priority": "high", "reason": "Hot lead asked for a call", "requires_human_approval": False}
    return NextActionRecommendation.model_validate({**base, **overrides})


def draft(**overrides: object) -> FollowupDraft:
    base = {"channel": "whatsapp", "message": "Hi Tomer, did you get a chance to review the routing plan with your team?",
                "objective": "Confirm review", "tone": "warm", "requires_human_approval": True}
    return FollowupDraft.model_validate({**base, **overrides})


class TestQualification:
    def test_valid_result_passes(self) -> None:
        assert validate_qualification(qualification()) == []

    def test_qualified_without_positive_signals_fails(self) -> None:
        assert validate_qualification(qualification(positive_signals=[]))

    def test_unqualified_needs_reasons(self) -> None:
        assert validate_qualification(qualification(qualified=False, positive_signals=[]))
        assert validate_qualification(qualification(qualified=False, missing_information=["Budget"])) == []

    def test_guardrail_rejects_malformed_json(self) -> None:
        output = TaskOutput(description="d", raw="not json", agent="a")
        ok, message = qualification_guardrail(output)
        assert not ok and "QualificationResult" in message

    def test_guardrail_attaches_parsed_model(self) -> None:
        output = TaskOutput(description="d", raw=qualification().model_dump_json(), agent="a")
        ok, result = qualification_guardrail(output)
        assert ok and isinstance(result.pydantic, QualificationResult)


class TestScoring:
    def test_consistent_scores_pass(self) -> None:
        assert validate_ai_score(score()) == []

    def test_overall_far_from_components_fails(self) -> None:
        assert validate_ai_score(score(overall_ai_score=10))

    def test_requires_two_reasons(self) -> None:
        assert validate_ai_score(score(reasons=["only one"]))


class TestAction:
    business = BusinessProfile(
        id="b1", slug="b1", name="B1",
        ai=AIConfiguration(allowed_actions=[NextAction.CALL, NextAction.SEND_EMAIL, NextAction.WAIT]),
    )
    validate = staticmethod(make_action_validator(business, clock=lambda: NOW))

    def test_allowed_action_passes(self) -> None:
        assert self.validate(recommendation(due_at=NOW + timedelta(hours=1))) == []

    def test_disallowed_action_fails(self) -> None:
        assert any("not allowed" in e for e in self.validate(recommendation(action="send_proposal")))

    def test_approval_required_action_must_request_approval(self) -> None:
        errors = self.validate(recommendation(action="send_email", requires_human_approval=False))
        assert any("requires human approval" in e for e in errors)
        assert self.validate(recommendation(action="send_email", requires_human_approval=True)) == []

    def test_passive_action_cannot_be_critical(self) -> None:
        assert self.validate(recommendation(action="wait", priority=Priority.CRITICAL))

    def test_due_at_in_past_fails(self) -> None:
        assert self.validate(recommendation(due_at=NOW - timedelta(days=1)))

    def test_naive_due_at_treated_as_utc(self) -> None:
        naive_future = (NOW + timedelta(hours=2)).replace(tzinfo=None)
        assert self.validate(recommendation(due_at=naive_future)) == []


class TestMessaging:
    business = BusinessProfile(id="b1", slug="b1", name="B1")
    lead = LeadSnapshot(id="l1", business_id="b1", source="web", status="new", budget=90000,
                        created_at=datetime(2026, 1, 1, tzinfo=UTC))
    validate = staticmethod(make_messaging_validator(business, lead))

    def test_contextual_draft_passes(self) -> None:
        assert self.validate(draft()) == []

    def test_invented_price_fails(self) -> None:
        assert any("prices" in e for e in self.validate(draft(message="Our package is only ₪4,900 per month.")))

    def test_leads_own_budget_is_allowed(self) -> None:
        assert self.validate(draft(message="You mentioned a budget of 90,000 ILS — that works for phase one.")) == []

    def test_discount_fails(self) -> None:
        assert self.validate(draft(message="Sign this week and get a 20% off discount!"))

    def test_completed_action_claim_fails(self) -> None:
        assert self.validate(draft(message="I've booked a call for Sunday at 10:00."))
        assert self.validate(draft(message="The proposal has been sent to your inbox."))

    def test_sms_length_limit(self) -> None:
        assert self.validate(draft(channel=Channel.SMS, message="x" * 400))

    def test_email_needs_subject(self) -> None:
        assert self.validate(draft(channel=Channel.EMAIL, subject=None))

    def test_low_autonomy_requires_approval(self) -> None:
        assert self.validate(draft(requires_human_approval=False))
        autonomous = self.business.model_copy(update={"ai": AIConfiguration(autonomy_level=AutonomyLevel.LOW_RISK_AUTOMATION)})
        assert make_messaging_validator(autonomous, self.lead)(draft(requires_human_approval=False)) == []

    def test_reply_to_hebrew_lead_must_be_in_hebrew(self) -> None:
        validate = make_messaging_validator(self.business, self.lead, "שלום, כמה עולה שיעור טיסת היכרות?")
        assert any("same language" in e for e in validate(draft(message="Hi, happy to help with an intro flight.")))
        assert validate(draft(message="היי, נשמח לעזור עם טיסת היכרות. מתי נוח לך, שישי או שבת?")) == []

    def test_reply_keeps_other_non_latin_scripts(self) -> None:
        validate = make_messaging_validator(self.business, self.lead, "Здравствуйте, сколько стоит урок?")
        assert validate(draft(message="Hi, thanks for writing!"))
        assert validate(draft(message="Здравствуйте! Когда вам удобно поговорить?")) == []

    def test_latin_brand_names_in_a_hebrew_reply_pass(self) -> None:
        validate = make_messaging_validator(self.business, self.lead, "שלום, אני מתעניין")
        assert validate(draft(message="היי, תודה שפנית ל-Jenia Aviation! מתי נוח לדבר?")) == []

    def test_latin_or_short_lead_message_sets_no_script(self) -> None:
        for message in ("Hola, cuánto cuesta?", "hi", None):
            validate = make_messaging_validator(self.business, self.lead, message)
            assert validate(draft()) == []

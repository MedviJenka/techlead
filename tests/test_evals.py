"""The evaluation harness itself, run with a scripted LLM. The real-model run is `python -m ai.evals`."""

from ai.crews.lead_intelligence.crew import LeadIntelligenceCrew, LeadIntelligenceResult
from ai.data.sample_store import InMemoryLeadStore
from ai.evals import LEAD_INTELLIGENCE_CASES, RANKING, EvalCase, check_case, check_ranking, run_lead_intelligence_eval
from ai.schemas import NextAction, Priority
from ai.skill_library import SkillLibrary
from tests.conftest import BUSINESS_ID, make_crew
from tests.fakes import ScriptedLLM
from tests.test_crews import AI_SCORE, QUALIFIED, call_now

HOT = EvalCase("lead_008", "hot", qualified=True, min_score=80, actions=frozenset({NextAction.CALL}),
               min_priority=Priority.HIGH)


def hot_result() -> LeadIntelligenceResult:
    result = LeadIntelligenceResult(qualification=QUALIFIED, ai_score=AI_SCORE, recommendation=call_now())
    return result.model_copy(deep=True)  # tests mutate it; QUALIFIED and AI_SCORE are shared


def hot_script() -> ScriptedLLM:
    return ScriptedLLM({"qualify_lead_task": [QUALIFIED], "score_lead_task": [AI_SCORE],
                        "recommend_next_action_task": [call_now()]})


def lead_crew(store: InMemoryLeadStore, llm: ScriptedLLM, skills: SkillLibrary) -> LeadIntelligenceCrew:
    return make_crew(LeadIntelligenceCrew, store, llm, skills)


class TestCases:
    def test_every_case_is_a_sample_lead(self, store: InMemoryLeadStore) -> None:
        for case in LEAD_INTELLIGENCE_CASES:
            store.get_lead(BUSINESS_ID, case.lead_id)

    def test_ranking_groups_have_cases(self) -> None:
        case_ids = {case.lead_id for case in LEAD_INTELLIGENCE_CASES}
        higher, lower = RANKING
        assert higher <= case_ids and lower <= case_ids and not higher & lower


class TestCheckCase:
    def test_matching_answer_passes(self) -> None:
        assert check_case(HOT, hot_result()) == []

    def test_reports_every_mismatch(self) -> None:
        result = hot_result()
        result.qualification.qualified = False
        result.ai_score.overall_ai_score = 40
        result.recommendation.action = NextAction.NURTURE
        result.recommendation.priority = Priority.LOW

        failures = check_case(HOT, result)

        assert len(failures) == 4
        assert any("overall_ai_score=40" in failure for failure in failures)

    def test_unset_expectations_are_not_checked(self) -> None:
        result = hot_result()
        result.qualification.qualified = False
        result.recommendation.action = NextAction.CLOSE_LOST
        assert check_case(EvalCase("lead_001", "anything goes"), result) == []


class TestCheckRanking:
    def test_hot_above_cold_passes(self) -> None:
        assert check_ranking({"lead_003": 90, "lead_008": 95, "lead_004": 30, "lead_007": 20}) == []

    def test_tie_or_inversion_fails(self) -> None:
        failures = check_ranking({"lead_003": 30, "lead_008": 95, "lead_004": 30, "lead_007": 20})
        assert failures == ["lead_003 scored 30, not above lead_004 (30)"]

    def test_missing_scores_are_skipped(self) -> None:
        assert check_ranking({"lead_008": 95}) == []


class TestRun:
    def test_passing_run(self, store: InMemoryLeadStore, skill_library: SkillLibrary) -> None:
        report = run_lead_intelligence_eval(store, lambda: lead_crew(store, hot_script(), skill_library),
                                            BUSINESS_ID, [HOT], model="scripted", min_pass_rate=1.0)

        assert report.passed
        assert report.cases[0].result is not None
        assert "Result: PASS" in report.render()

    def test_wrong_answer_fails_the_run(self, store: InMemoryLeadStore, skill_library: SkillLibrary) -> None:
        cold = EvalCase("lead_007", "cold", qualified=False, max_score=45)
        report = run_lead_intelligence_eval(store, lambda: lead_crew(store, hot_script(), skill_library),
                                            BUSINESS_ID, [HOT, cold], model="scripted", min_pass_rate=0.8)

        assert report.pass_rate == 0.5
        assert not report.passed
        assert report.ranking_failures  # lead_008 tied with lead_007

    def test_crew_error_is_a_failed_case(self, store: InMemoryLeadStore, skill_library: SkillLibrary) -> None:
        llm = ScriptedLLM({"qualify_lead_task": [QUALIFIED]})  # no answer for scoring: the run raises
        report = run_lead_intelligence_eval(store, lambda: lead_crew(store, llm, skill_library),
                                            BUSINESS_ID, [HOT], model="scripted", min_pass_rate=0.0)

        assert report.cases[0].error is not None
        assert not report.cases[0].passed
        assert "Result:" in report.render()

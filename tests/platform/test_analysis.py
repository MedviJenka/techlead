"""The app -> CrewAI bridge (`app.analysis`), analysis queueing and NewLeadFlow, with in-memory repositories.

The end-to-end test runs the real LeadIntelligenceCrew (agents, tools, guardrails) on a scripted LLM.
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from ai.ports import NotFoundError
from ai.schemas import (
    ActivitySnapshot,
    AIScoreResult,
    BusinessProfile,
    Channel,
    LeadSnapshot,
    NextAction,
    NextActionRecommendation,
    Priority,
    QualificationResult,
)
from ai.schemas.enums import ActivityType
from app.analysis import (
    CrewAnalysisEngine,
    SingleLeadReadService,
    missing_ai_configuration,
    to_business_profile,
    to_lead_snapshot,
)
from app.analysis.cost import TokenPrices
from app.analysis.flow import LeadRoute, NewLeadFlow, route_for
from app.core.errors import NotFoundError as AppNotFoundError
from app.intelligence import Event, ai_score
from app.models import AnalysisJobStatus, AnalysisTrigger, Lead
from app.schemas import ImportEnvelope
from app.services.lead import LeadService
from tests.fakes import ScriptedLLM
from tests.platform.factories import raw_lead
from tests.platform.memory import NOW, FakeStore, make_business, make_service

QUALIFIED = QualificationResult(
    qualified=True,
    confidence=0.9,
    intent="high",
    urgency="high",
    fit="good",
    positive_signals=["Budget defined", "Replied the same day"],
    summary="Clear need, defined budget and an active conversation.",
)
AI_SCORE = AIScoreResult(
    intent_score=90,
    urgency_score=85,
    fit_score=80,
    engagement_score=75,
    sentiment_score=80,
    overall_ai_score=90,
    reasons=["Defined budget", "Replied quickly"],
)


def _recommendation() -> NextActionRecommendation:
    return NextActionRecommendation(
        action=NextAction.CALL,
        priority=Priority.CRITICAL,
        reason="Ready to talk; call while interest is high.",
        due_at=NOW + timedelta(hours=1),
        requires_human_approval=False,
    )


class FakeEngine:
    def __init__(self, error: Exception | None = None, usage: Any = None) -> None:
        self.error = error
        self.usage = usage
        self.calls: list[tuple[BusinessProfile, LeadSnapshot, list[ActivitySnapshot]]] = []

    async def analyze(self, business: BusinessProfile, lead: LeadSnapshot, activities: list[ActivitySnapshot]) -> Any:
        self.calls.append((business, lead, activities))
        if self.error:
            raise self.error
        return SimpleNamespace(
            qualification=QUALIFIED, ai_score=AI_SCORE, recommendation=_recommendation(), usage=self.usage
        )


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def business() -> Any:
    return make_business({"scoring": {"base_score": 40, "rules": []}})


@pytest.fixture
def service(business: Any, store: FakeStore) -> LeadService:
    return make_service(business, store)


async def _imported(service: LeadService, business_id: uuid.UUID, index: int = 0) -> Lead:
    result = await service.import_batch(business_id, ImportEnvelope(leads=[raw_lead(index)]))
    lead_id = result.results[0].lead_id
    assert lead_id is not None
    return await service.get(business_id, lead_id)


# --- AI score source ---


def test_latest_ai_analysis_score_wins_over_the_imported_one() -> None:
    lead = Lead.model_validate(
        {
            "id": uuid.uuid4(),
            "business_id": uuid.uuid4(),
            "external_id": None,
            "source": "web",
            "status": "new",
            "priority": None,
            "first_name": None,
            "last_name": None,
            "email": None,
            "phone": None,
            "company_name": None,
            "notes": None,
            "lead_score": None,
            "sentiment": None,
            "ai_summary": None,
            "recommended_action": None,
            "custom_fields": {},
            "raw_payload": {"ai": {"lead_score": 30}},
            "last_contact_at": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
    )
    older = Event(ActivityType.AI_ANALYSIS, NOW - timedelta(days=2), {"ai_score": 50})
    newer = Event(ActivityType.AI_ANALYSIS, NOW - timedelta(days=1), {"ai_score": 70})
    broken = Event(ActivityType.AI_ANALYSIS, NOW, {"ai_score": "high"})

    assert ai_score(lead, []) == 30
    assert ai_score(lead, [newer, older, broken]) == 70


# --- snapshots and the read service ---


async def test_snapshots_map_the_imported_lead(service: LeadService, business: Any, store: FakeStore) -> None:
    lead = await _imported(service, business.id)  # lead_001
    snapshot = to_lead_snapshot(lead, await store.all_for_lead(business.id, lead.id))

    assert (snapshot.id, snapshot.business_id, snapshot.full_name) == (str(lead.id), str(business.id), "Daniel Cohen")
    assert (snapshot.budget, snapshot.currency, snapshot.timeframe) == (2500000, "ILS", "1-3 months")
    assert (snapshot.product_interest, snapshot.company_industry, snapshot.company_size) == (
        "premium apartment",
        "real_estate",
        "11-50",
    )
    assert (snapshot.preferred_channel, snapshot.contact_attempts, snapshot.replied) == (Channel.WHATSAPP, 0, False)


def test_business_profile_carries_ai_settings_and_falls_back_to_defaults() -> None:
    business = make_business({"scoring": {"ai_weight": 0.25}})
    business.ai_configuration = {"tone": "formal", "language": "Hebrew"}

    profile = to_business_profile(business)

    assert (profile.id, profile.ai.tone, profile.ai.language) == (str(business.id), "formal", "Hebrew")
    assert (profile.scoring.deterministic_weight, profile.scoring.ai_weight) == (0.75, 0.25)
    business.ai_configuration = {"autonomy_level": "not a level"}
    assert to_business_profile(business).ai.autonomy_level == profile.ai.autonomy_level


async def test_read_service_exposes_only_the_analysed_lead(
    service: LeadService, business: Any, store: FakeStore
) -> None:
    lead = await _imported(service, business.id)
    activities = await store.all_for_lead(business.id, lead.id)
    profile = to_business_profile(business)
    snapshot = to_lead_snapshot(lead, activities)
    read = SingleLeadReadService(profile, snapshot, [])

    assert read.get_lead(profile.id, snapshot.id) == snapshot
    with pytest.raises(NotFoundError):
        read.get_lead(str(uuid.uuid4()), snapshot.id)
    with pytest.raises(NotFoundError):
        read.list_activities(profile.id, str(uuid.uuid4()))


# --- queueing: new leads and manual requests ---


async def test_new_lead_is_queued_for_analysis_in_the_same_save(
    service: LeadService, business: Any, store: FakeStore
) -> None:
    lead = await service.create(business.id, _create(first_name="Dana"))
    imported = await _imported(service, business.id)

    queued = [(job.lead_id, job.trigger, job.status) for job in store.jobs.jobs]
    assert queued == [
        (lead.id, AnalysisTrigger.LEAD_CREATED, AnalysisJobStatus.PENDING),
        (imported.id, AnalysisTrigger.LEAD_CREATED, AnalysisJobStatus.PENDING),
    ]
    # Updates and contact matches do not queue another run.
    await service.update(business.id, lead.id, _update(notes="Called back"))
    await service.create(business.id, _create(first_name="Dana", email=imported.email))
    assert len(store.jobs.jobs) == 2


async def test_business_can_turn_off_automatic_analysis(store: FakeStore) -> None:
    business = make_business({})
    business.ai_configuration = {"auto_analyze": False}
    service = make_service(business, store)

    lead = await service.create(business.id, _create())

    assert store.jobs.jobs == []
    job = await service.request_analysis(business.id, lead.id)  # a manual request still works
    assert job.trigger is AnalysisTrigger.MANUAL


async def test_request_returns_the_open_job_instead_of_queueing_another(
    service: LeadService, business: Any, store: FakeStore
) -> None:
    lead = await service.create(business.id, _create())

    job = await service.request_analysis(business.id, lead.id)

    assert job.trigger is AnalysisTrigger.LEAD_CREATED and len(store.jobs.jobs) == 1
    with pytest.raises(AppNotFoundError):
        await service.request_analysis(business.id, uuid.uuid4())


# --- NewLeadFlow ---


def _flow(service: LeadService, engine: Any, prices: TokenPrices | None = None) -> NewLeadFlow:
    return NewLeadFlow(service, engine, "openai/test-model", prices)


async def test_flow_saves_summary_action_blended_score_and_routes(
    service: LeadService, business: Any, store: FakeStore
) -> None:
    lead = await service.create(business.id, _create(first_name="Dana"))
    engine = FakeEngine()

    outcome = await _flow(service, engine).run(business.id, lead.id)

    saved = store.leads[lead.id]
    assert engine.calls[0][1].first_name == "Dana"
    assert (saved.ai_summary, saved.recommended_action) == (QUALIFIED.summary, "call")
    # Rules score 40 (no rules), AI 90: 40 * 0.6 + 90 * 0.4 = 60, which is medium (not the AI's "critical").
    assert (saved.lead_score, saved.priority) == (60, Priority.MEDIUM)
    assert (outcome.lead, outcome.route, outcome.cost) == (saved, LeadRoute.WARM, None)
    assert store.types(lead.id)[-3:] == [
        ActivityType.AI_ANALYSIS,
        ActivityType.LEAD_UPDATED,
        ActivityType.SCORE_CHANGED,
    ]
    recorded = next(a for a in store.activities if a.activity_type is ActivityType.AI_ANALYSIS)
    assert (recorded.metadata["ai_score"], recorded.metadata["recommended_action"]) == (90, "call")
    assert recorded.metadata["qualification"]["qualified"] is True
    # The AI score sticks: a later edit keeps blending it in.
    edited = await service.update(business.id, lead.id, _update(notes="Called back"))
    assert edited.lead_score == 60


async def test_flow_records_the_cost_of_the_run(service: LeadService, business: Any, store: FakeStore) -> None:
    lead = await service.create(business.id, _create())
    usage = SimpleNamespace(
        prompt_tokens=20_000, cached_prompt_tokens=4_000, completion_tokens=2_000, successful_requests=9
    )
    prices = TokenPrices(input=Decimal("1.25"), output=Decimal("10"), cached_input=Decimal("0.125"))

    outcome = await _flow(service, FakeEngine(usage=usage), prices).run(business.id, lead.id)

    # (16k * 1.25 + 4k * 0.125 + 2k * 10) per million tokens.
    assert outcome.cost is not None and outcome.cost.cost_usd == Decimal("0.040500")
    recorded = next(a for a in store.activities if a.activity_type is ActivityType.AI_ANALYSIS)
    assert recorded.metadata["cost"] == {
        "model": "openai/test-model",
        "prompt_tokens": 20_000,
        "cached_prompt_tokens": 4_000,
        "completion_tokens": 2_000,
        "requests": 9,
        "cost_usd": "0.040500",
    }


async def test_repeat_analysis_records_an_activity_even_when_nothing_changes(
    service: LeadService, business: Any, store: FakeStore
) -> None:
    lead = await service.create(business.id, _create())
    await _flow(service, FakeEngine()).run(business.id, lead.id)
    before = len(store.activities)

    await _flow(service, FakeEngine()).run(business.id, lead.id)

    assert [a.activity_type for a in store.activities[before:]] == [ActivityType.AI_ANALYSIS]


async def test_failed_analysis_changes_nothing(service: LeadService, business: Any, store: FakeStore) -> None:
    lead = await service.create(business.id, _create())
    before = len(store.activities)

    with pytest.raises(RuntimeError, match="provider down"):
        await _flow(service, FakeEngine(RuntimeError("provider down"))).run(business.id, lead.id)

    assert len(store.activities) == before and store.leads[lead.id] == lead


@pytest.mark.parametrize(
    ("priority", "route"),
    [
        (Priority.CRITICAL, LeadRoute.HOT),
        (Priority.HIGH, LeadRoute.HOT),
        (Priority.MEDIUM, LeadRoute.WARM),
        (Priority.LOW, LeadRoute.COLD),
        (None, LeadRoute.COLD),
    ],
)
def test_priority_route(priority: Priority | None, route: LeadRoute) -> None:
    assert route_for(priority) is route


async def test_analysis_state_shows_the_open_job_and_the_last_saved_result(
    service: LeadService, business: Any, store: FakeStore
) -> None:
    lead = await service.create(business.id, _create())
    state = await service.analysis_state(business.id, lead.id)
    assert state.job is not None and state.job.status is AnalysisJobStatus.PENDING and state.result is None

    await _flow(service, FakeEngine()).run(business.id, lead.id)

    state = await service.analysis_state(business.id, lead.id)
    assert state.result is not None
    assert state.result.qualification == QUALIFIED and state.result.recommendation.action is NextAction.CALL


def test_ai_configuration_needs_an_api_key_for_openai_models() -> None:
    def config(**fields: Any) -> Any:
        values = {"AI_REASONING_MODEL": None, "OPENAI_MODEL": "gpt-4o-mini", "OPENAI_API_KEY": None} | fields
        return SimpleNamespace(**values)

    assert "OPENAI_API_KEY" in (missing_ai_configuration(config()) or "")
    assert missing_ai_configuration(config(OPENAI_API_KEY="sk-test")) is None
    assert missing_ai_configuration(config(OPENAI_MODEL="anthropic/claude-sonnet-5-5")) is None


async def test_real_crew_runs_on_bridged_snapshots(service: LeadService, business: Any, store: FakeStore) -> None:
    lead = await _imported(service, business.id, 7)  # lead_008
    llm = ScriptedLLM(
        {
            "qualify_lead_task": [QUALIFIED],
            "score_lead_task": [AI_SCORE],
            "recommend_next_action_task": [_recommendation().model_copy(update={"due_at": None})],
        }
    )

    outcome = await _flow(service, CrewAnalysisEngine(lambda tier: llm)).run(business.id, lead.id)

    assert llm.calls == ["qualify_lead_task", "score_lead_task", "recommend_next_action_task"]
    assert outcome.lead.recommended_action == "call"
    assert store.leads[lead.id].ai_summary == QUALIFIED.summary


def _create(**fields: Any) -> Any:
    from app.schemas import LeadCreate

    return LeadCreate.model_validate({"source": "web"} | fields)


def _update(**fields: Any) -> Any:
    from app.schemas import LeadUpdate

    return LeadUpdate.model_validate(fields)

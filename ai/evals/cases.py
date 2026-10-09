"""Expected behaviour of LeadIntelligenceCrew on docs/files/sample_raw_leads.json.

Expectations are bands, not exact answers: an LLM run is not deterministic, and several answers can be
right for the same lead. A field left as None is not checked. The sample business sells AI lead
management (industry: saas), so leads that want something else are not asserted on fit.
"""

from dataclasses import dataclass

from ai.schemas import NextAction, Priority

ACTIVE_OUTREACH = frozenset({
    NextAction.CALL, NextAction.SEND_WHATSAPP, NextAction.SEND_EMAIL,
    NextAction.REQUEST_INFORMATION, NextAction.SCHEDULE_DEMO,
})
LOW_EFFORT = frozenset({NextAction.NURTURE, NextAction.WAIT, NextAction.CLOSE_LOST})


@dataclass(frozen=True)
class EvalCase:
    lead_id: str
    rationale: str
    qualified: bool | None = None
    min_score: int = 0
    max_score: int = 100
    actions: frozenset[NextAction] | None = None
    min_priority: Priority = Priority.LOW
    max_priority: Priority = Priority.CRITICAL


LEAD_INTELLIGENCE_CASES: tuple[EvalCase, ...] = (
    EvalCase(
        "lead_001", "Big budget but buys an apartment, not lead management: only the run itself is checked.",
    ),
    EvalCase(
        "lead_002", "Replied, but budget and timeframe unknown: qualify further, not a top priority.",
        min_score=30, max_score=85, actions=ACTIVE_OUTREACH, max_priority=Priority.HIGH,
    ),
    EvalCase(
        "lead_003", "Budget, this-quarter timeframe, clear need, engaged: hot.",
        qualified=True, min_score=70,
        actions=frozenset({NextAction.CALL, NextAction.SCHEDULE_DEMO, NextAction.SEND_PROPOSAL,
                           NextAction.SEND_WHATSAPP}),
        min_priority=Priority.HIGH,
    ),
    EvalCase(
        "lead_004", "Researching, 6+ months, no budget, did not reply: nurture.",
        qualified=False, max_score=50,
        actions=frozenset({NextAction.NURTURE, NextAction.WAIT, NextAction.SEND_EMAIL,
                           NextAction.REQUEST_INFORMATION}),
        max_priority=Priority.MEDIUM,
    ),
    EvalCase(
        "lead_005", "Proposal sent, budget, 30 days, replied: follow up on the proposal.",
        qualified=True, min_score=65,
        actions=frozenset({NextAction.CALL, NextAction.SEND_WHATSAPP, NextAction.SEND_EMAIL,
                           NextAction.SEND_PROPOSAL, NextAction.SCHEDULE_DEMO, NextAction.ESCALATE_TO_MANAGER}),
        min_priority=Priority.MEDIUM,
    ),
    EvalCase(
        "lead_006", "Good fit, 1-2 months, no budget, not contacted yet: reach out and qualify.",
        min_score=40, max_score=90, actions=ACTIVE_OUTREACH,
    ),
    EvalCase(
        "lead_007", "Four attempts, never replied, only asked for a price: stop chasing.",
        qualified=False, max_score=45,
        actions=LOW_EFFORT | {NextAction.SEND_WHATSAPP},
        max_priority=Priority.MEDIUM,
    ),
    EvalCase(
        "lead_008", "Immediate need, 90k budget, replied on first call: call now.",
        qualified=True, min_score=80,
        actions=frozenset({NextAction.CALL, NextAction.SCHEDULE_DEMO, NextAction.SEND_PROPOSAL}),
        min_priority=Priority.HIGH,
    ),
    EvalCase(
        "lead_009", "Budget, this quarter, replied: move forward.",
        qualified=True, min_score=55,
        actions=ACTIVE_OUTREACH | {NextAction.SEND_PROPOSAL},
        min_priority=Priority.MEDIUM,
    ),
    EvalCase(
        "lead_010", "Clear use case, 1-3 months, no budget, not contacted yet: reach out and qualify.",
        min_score=40, max_score=90, actions=ACTIVE_OUTREACH,
    ),
)

# Every lead in the first group must get a higher AI score than every lead in the second.
RANKING: tuple[frozenset[str], frozenset[str]] = (
    frozenset({"lead_003", "lead_008"}),
    frozenset({"lead_004", "lead_007"}),
)

"""Industry presets (MAIN_PLAN §66): a new business starts from its industry's custom fields, scoring, follow-up timing
and AI instructions, and only adjusts them. Everything a preset sets stays editable in Settings.
"""

from dataclasses import dataclass

from app.schemas.configuration import (
    BusinessConfiguration,
    Condition,
    CustomFieldDefinition,
    FollowUpConfig,
    ScoringConfig,
    ScoringRule,
)


@dataclass(frozen=True)
class IndustryPreset:
    key: str
    label: str
    industry: str
    description: str
    configuration: BusinessConfiguration
    custom_fields: list[CustomFieldDefinition]
    # Business instructions every agent reads (``AIConfiguration.instructions``).
    instructions: str
    tone: str = "professional, warm and concise"


def _rule(rule_id: str, label: str, points: int, *conditions: Condition) -> ScoringRule:
    return ScoringRule(id=rule_id, label=label, points=points, when=list(conditions))


def _when(fact: str, op: str, value: object = None) -> Condition:
    return Condition.model_validate({"fact": fact, "op": op, "value": value})


def _select(key: str, label: str, *options: str) -> CustomFieldDefinition:
    return CustomFieldDefinition(key=key, label=label, type="select", options=list(options))


def _field(key: str, label: str, field_type: str) -> CustomFieldDefinition:
    return CustomFieldDefinition.model_validate({"key": key, "label": label, "type": field_type})


_REAL_ESTATE_INSTRUCTIONS = """\
Real-estate leads (buyers, renters, sellers and investors).

Qualify on: area or neighborhood; property type and rooms; budget (compare with realistic prices in that area — a \
large gap is a fit problem); financing (cash or a pre-approved mortgage is a strong signal, "not started" lowers \
urgency); move-in timing (under 3 months is urgent, "just looking" is nurture); investor vs. own residence; whether \
they must sell a property first (a dependency that delays the purchase).

Strong signals: approved financing, a specific area and room count, asks for viewings, cash buyer, relocation date.
Weak signals: no budget and no area, "just checking prices", open-ended timing, wants to rent when we only sell.

Next actions: specific requirements with financing in place -> call and book viewings quickly (good properties go \
fast). Missing budget or area -> request_information.

First reply on WhatsApp: answer within minutes, by first name if known. Thank them, ask at most two of the missing \
questions (area, budget, rooms, move-in timing, financing) and offer a call or a viewing. Short, friendly, no lists. \
Never quote prices, availability or specific properties that are not in the data, and never promise a viewing time.\
"""

REAL_ESTATE = IndustryPreset(
    key="real_estate",
    label="Real estate",
    industry="Real estate",
    description="Buyers, renters and investors: area, budget, rooms, financing and move-in timing.",
    configuration=BusinessConfiguration(
        scoring=ScoringConfig(
            base_score=40,
            ai_weight=0.4,
            rules=[
                _rule("budget_known", "Budget known", 10, _when("budget_known", "eq", True)),
                _rule("move_within_90_days", "Moving within 3 months", 10, _when("timeframe_days", "lte", 90)),
                _rule("move_within_30_days", "Moving within a month", 10, _when("timeframe_days", "lte", 30)),
                _rule(
                    "financing_ready", "Cash or mortgage pre-approved", 20,
                    _when("custom_fields.financing", "in", ["cash", "pre_approved"]),
                ),
                _rule("area_known", "Area known", 5, _when("custom_fields.area", "exists")),
                _rule("wants_viewing", "Asked for a viewing", 15, _when("custom_fields.viewing_requested", "eq", True)),
                _rule("responded", "Lead responded", 10, _when("replied", "eq", True)),
                _rule(
                    "must_sell_first", "Must sell a property first", -10,
                    _when("custom_fields.property_to_sell", "eq", True),
                ),
                _rule(
                    "financing_not_started", "Financing not started", -5,
                    _when("custom_fields.financing", "eq", "not_started"),
                ),
                _rule(
                    "no_contact_7_days", "No contact for over 7 days", -10, _when("days_since_last_contact", "gt", 7)
                ),
                _rule("ignored_follow_ups", "Three ignored follow-ups", -15, _when("ignored_follow_ups", "gte", 3)),
            ],
        ),
        follow_up=FollowUpConfig.model_validate(
            {
                # Real-estate leads go cold in minutes: hot ones within 15 minutes, everyone the same day.
                "first_response_hours": {"critical": 0.25, "high": 0.5, "medium": 2, "low": 24},
                "interval_hours": {"critical": 24, "high": 24, "medium": 48, "low": 168},
                "status_interval_hours": {"viewing_scheduled": 24, "offer_made": 48, "proposal_sent": 48},
            }
        ),
    ),
    custom_fields=[
        _select("deal_type", "Looking to", "buy", "rent", "sell", "invest"),
        _select("property_type", "Property type", "apartment", "house", "penthouse", "land", "commercial", "other"),
        _field("area", "Area / neighborhood", "text"),
        _field("rooms", "Rooms", "number"),
        _field("budget", "Budget", "number"),
        _field("timeframe", "Move-in timing", "text"),
        _select("financing", "Financing", "cash", "pre_approved", "in_process", "not_started"),
        _field("property_to_sell", "Must sell a property first", "boolean"),
        _field("viewing_requested", "Asked for a viewing", "boolean"),
    ],
    instructions=_REAL_ESTATE_INSTRUCTIONS,
)

PRESETS: dict[str, IndustryPreset] = {preset.key: preset for preset in (REAL_ESTATE,)}

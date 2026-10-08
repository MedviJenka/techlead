"""App rows -> the read-only snapshots the AI layer reads (`ai.schemas`). Pure mapping, no I/O."""

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from ai.schemas import ActivitySnapshot, ActivityType, AIConfiguration, BusinessProfile, LeadSnapshot, ScoringWeights
from app.intelligence.facts import Event, lead_facts
from app.models import Activity, Business, Lead
from app.schemas.configuration import BusinessConfiguration


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def to_business_profile(business: Business) -> BusinessProfile:
    try:
        ai = AIConfiguration.model_validate(business.ai_configuration)
    except ValidationError:
        ai = AIConfiguration()
    weight = BusinessConfiguration.from_stored(business.configuration).scoring.ai_weight
    return BusinessProfile(
        id=str(business.id),
        slug=business.slug,
        name=business.name,
        industry=business.industry,
        timezone=business.timezone,
        ai=ai,
        scoring=ScoringWeights(deterministic_weight=1 - weight, ai_weight=weight),
    )


def to_activity_snapshot(activity: Activity) -> ActivitySnapshot:
    return ActivitySnapshot(
        id=str(activity.id),
        business_id=str(activity.business_id),
        lead_id=str(activity.lead_id),
        activity_type=activity.activity_type,
        channel=activity.channel,
        description=activity.description,
        created_at=activity.created_at,
        metadata=activity.metadata,
    )


def to_lead_snapshot(lead: Lead, activities: Sequence[Activity]) -> LeadSnapshot:
    """The lead as agents see it. Engagement counts come from the same facts the scoring rules use."""
    events = [Event(a.activity_type, a.created_at, a.metadata) for a in activities]
    facts = lead_facts(lead, events, lead.updated_at)
    company = lead.raw_payload.get("company")
    company = company if isinstance(company, dict) else {}
    channel = next((a.channel for a in activities if a.activity_type is ActivityType.LEAD_CREATED and a.channel), None)
    return LeadSnapshot(
        id=str(lead.id),
        business_id=str(lead.business_id),
        external_id=lead.external_id,
        source=lead.source,
        status=lead.status,
        priority=lead.priority.value if lead.priority else None,
        first_name=lead.first_name,
        last_name=lead.last_name,
        email=lead.email,
        phone=lead.phone,
        preferred_channel=channel,
        company_name=lead.company_name,
        company_industry=_text(company.get("industry")),
        company_size=_text(company.get("size")),
        product_interest=_text(lead.custom_fields.get("product_or_service")),
        budget=_number(lead.custom_fields.get("budget")),
        currency=_text(lead.custom_fields.get("currency")),
        timeframe=_text(lead.custom_fields.get("timeframe")),
        notes=lead.notes,
        contact_attempts=facts["contact_attempts"],
        replied=facts["replied"],
        lead_score=lead.lead_score,
        sentiment=lead.sentiment.value if lead.sentiment else None,
        ai_summary=lead.ai_summary,
        recommended_action=lead.recommended_action,
        custom_fields=lead.custom_fields,
        created_at=lead.created_at,
        last_contact_at=lead.last_contact_at,
    )

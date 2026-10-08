"""In-memory LeadReadService backed by docs/files/sample_raw_leads.json.

Stand-in for the PostgreSQL-backed application services until Phases 1-3 land.
"""

import json
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ai.ports import NotFoundError
from ai.schemas import (
    ActivitySnapshot,
    ActivityType,
    BusinessProfile,
    Channel,
    LeadSearchFilter,
    LeadSnapshot,
    LeadSortField,
    PipelineMetrics,
)

SAMPLE_LEADS_PATH = Path(__file__).resolve().parents[2] / "docs" / "files" / "sample_raw_leads.json"
SAMPLE_BUSINESS = BusinessProfile(id="biz_techlead", slug="techlead", name="Techlead", industry="saas")

STALE_AFTER = timedelta(days=5)
HOT_PRIORITIES = frozenset({"high", "critical"})
CLOSED_STATUSES = frozenset({"won", "lost", "closed_won", "closed_lost"})

_CHANNEL_ALIASES: dict[str, Channel] = {"whatsapp": Channel.WHATSAPP, "email": Channel.EMAIL, "phone": Channel.PHONE}


class InMemoryLeadStore:
    """Tenant-scoped, read-only lead store."""

    def __init__(
        self,
        businesses: Iterable[BusinessProfile],
        leads: Iterable[LeadSnapshot],
        activities: Iterable[ActivitySnapshot] = (),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._businesses = {b.id: b for b in businesses}
        self._leads = {(lead.business_id, lead.id): lead for lead in leads}
        self._activities = list(activities)
        self._clock = clock

    def get_business(self, business_id: str) -> BusinessProfile:
        try:
            return self._businesses[business_id]
        except KeyError:
            raise NotFoundError(f"Business {business_id} not found") from None

    def get_lead(self, business_id: str, lead_id: str) -> LeadSnapshot:
        try:
            return self._leads[(business_id, lead_id)]
        except KeyError:
            raise NotFoundError(f"Lead {lead_id} not found") from None

    def list_activities(self, business_id: str, lead_id: str, limit: int = 20) -> list[ActivitySnapshot]:
        self.get_lead(business_id, lead_id)
        matching = [a for a in self._activities if a.business_id == business_id and a.lead_id == lead_id]
        return sorted(matching, key=lambda a: a.created_at)[-limit:]

    def search_leads(self, business_id: str, search: LeadSearchFilter) -> list[LeadSnapshot]:
        now = self._clock()
        leads = [lead for (biz, _), lead in self._leads.items() if biz == business_id]
        matched = [lead for lead in leads if _matches(lead, search, now)]
        matched.sort(key=_sort_key(search.sort_by), reverse=search.descending)
        return matched[: search.limit]

    def get_pipeline_metrics(self, business_id: str) -> PipelineMetrics:
        self.get_business(business_id)
        now = self._clock()
        leads = [lead for (biz, _), lead in self._leads.items() if biz == business_id]
        scores = [lead.lead_score for lead in leads if lead.lead_score is not None]
        return PipelineMetrics(
            total_leads=len(leads),
            by_status=dict(Counter(lead.status for lead in leads)),
            by_source=dict(Counter(lead.source for lead in leads)),
            average_score=round(sum(scores) / len(scores), 1) if scores else None,
            hot_leads_not_contacted=sum(1 for lead in leads if _is_hot(lead) and lead.contact_attempts == 0),
            stale_leads=sum(1 for lead in leads if _is_stale(lead, now)),
            unanswered_proposals=sum(1 for lead in leads if lead.status == "proposal_sent" and not lead.replied),
        )


def _is_hot(lead: LeadSnapshot) -> bool:
    return (lead.priority or "") in HOT_PRIORITIES


def _is_stale(lead: LeadSnapshot, now: datetime) -> bool:
    if lead.status in CLOSED_STATUSES or lead.last_contact_at is None:
        return False
    return now - lead.last_contact_at > STALE_AFTER


def _matches(lead: LeadSnapshot, f: LeadSearchFilter, now: datetime) -> bool:
    checks = (
        not f.statuses or lead.status in f.statuses,
        not f.priorities or lead.priority in f.priorities,
        not f.sources or lead.source in f.sources,
        f.min_score is None or (lead.lead_score or 0) >= f.min_score,
        f.max_score is None or (lead.lead_score or 0) <= f.max_score,
        f.min_budget is None or (lead.budget is not None and lead.budget >= f.min_budget),
        f.max_budget is None or (lead.budget is not None and lead.budget <= f.max_budget),
        f.budget_known is None or (lead.budget is not None) == f.budget_known,
        f.not_contacted_for_days is None or _not_contacted_for(lead, f.not_contacted_for_days, now),
        not f.text or _text_matches(lead, f.text),
    )
    return all(checks)


def _not_contacted_for(lead: LeadSnapshot, days: int, now: datetime) -> bool:
    return lead.last_contact_at is None or now - lead.last_contact_at >= timedelta(days=days)


def _text_matches(lead: LeadSnapshot, text: str) -> bool:
    haystack = " ".join(filter(None, (lead.full_name, lead.company_name, lead.notes, lead.product_interest)))
    return text.lower() in haystack.lower()


def _sort_key(field: LeadSortField) -> Callable[[LeadSnapshot], Any]:
    epoch = datetime.min.replace(tzinfo=UTC)
    keys: dict[LeadSortField, Callable[[LeadSnapshot], Any]] = {
        LeadSortField.SCORE: lambda lead: lead.lead_score or 0,
        LeadSortField.CREATED_AT: lambda lead: lead.created_at,
        LeadSortField.LAST_CONTACT_AT: lambda lead: lead.last_contact_at or epoch,
        LeadSortField.BUDGET: lambda lead: lead.budget or 0,
    }
    return keys[field]


def parse_raw_lead(raw: dict[str, Any], business_id: str) -> LeadSnapshot:
    """Map one sample_raw_leads.json record onto the normalized lead model."""
    contact = raw.get("contact") or {}
    company = raw.get("company") or {}
    intent = raw.get("intent") or {}
    engagement = raw.get("engagement") or {}
    ai = raw.get("ai") or {}
    return LeadSnapshot(
        id=raw["lead_id"],
        business_id=business_id,
        external_id=raw["lead_id"],
        source=raw["source"],
        status=raw["status"],
        priority=raw.get("priority"),
        first_name=contact.get("first_name"),
        last_name=contact.get("last_name"),
        email=contact.get("email"),
        phone=contact.get("phone"),
        preferred_channel=_CHANNEL_ALIASES.get(contact.get("preferred_channel") or ""),
        company_name=company.get("name"),
        company_industry=company.get("industry"),
        company_size=company.get("size"),
        product_interest=intent.get("product_or_service"),
        budget=intent.get("budget"),
        currency=intent.get("currency"),
        timeframe=intent.get("timeframe"),
        notes=intent.get("notes"),
        contact_attempts=engagement.get("contact_attempts", 0),
        replied=engagement.get("replied", False),
        lead_score=ai.get("lead_score"),
        sentiment=ai.get("sentiment"),
        ai_summary=ai.get("summary"),
        recommended_action=ai.get("recommended_action"),
        custom_fields=raw.get("custom_fields") or {},
        created_at=raw["created_at"],
        last_contact_at=engagement.get("last_contact_at"),
    )


def derive_activities(lead: LeadSnapshot) -> list[ActivitySnapshot]:
    """The sample file has no activity log, so synthesize the minimum implied by each record."""
    activities = [
        ActivitySnapshot(
            id=f"{lead.id}_created",
            business_id=lead.business_id,
            lead_id=lead.id,
            activity_type=ActivityType.LEAD_CREATED,
            description=f"Lead received from {lead.source}",
            created_at=lead.created_at,
        )
    ]
    if lead.last_contact_at is not None:
        outcome = "customer replied" if lead.replied else "no reply yet"
        activities.append(
            ActivitySnapshot(
                id=f"{lead.id}_last_contact",
                business_id=lead.business_id,
                lead_id=lead.id,
                activity_type=ActivityType.PHONE_CALL if lead.preferred_channel == Channel.PHONE else ActivityType.LEAD_UPDATED,
                channel=lead.preferred_channel,
                description=f"Contact attempt #{lead.contact_attempts} ({outcome})",
                created_at=lead.last_contact_at,
            )
        )
    return activities


def load_sample_store(
    path: Path = SAMPLE_LEADS_PATH,
    business: BusinessProfile = SAMPLE_BUSINESS,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> InMemoryLeadStore:
    payload = json.loads(path.read_text(encoding="utf-8"))
    leads = [parse_raw_lead(raw, business.id) for raw in payload["leads"]]
    activities = [activity for lead in leads for activity in derive_activities(lead)]
    return InMemoryLeadStore([business], leads, activities, clock=clock)

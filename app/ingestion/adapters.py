"""Source adapters: one raw record -> ``AdaptedLead`` (MAIN_PLAN §7 ingestion pipeline).

Adapters only map and validate. Deduplication, persistence and activities belong to the services.
"""

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeIs

from pydantic import BaseModel, ConfigDict, ValidationError

from ai.schemas.enums import Channel
from app.schemas.common import RecordError
from app.schemas.lead import LeadImportData

# Ported from ai/data/sample_store.py (app must not import ai.data): preferred channels we can attribute.
_CHANNEL_ALIASES: dict[str, Channel] = {"whatsapp": Channel.WHATSAPP, "email": Channel.EMAIL, "phone": Channel.PHONE}

# Normalized field -> its location in a raw sample-shaped record, so errors point at what the client sent.
_RAW_LOCATIONS: dict[str, tuple[str, ...]] = {
    "external_id": ("lead_id",),
    "first_name": ("contact", "first_name"),
    "last_name": ("contact", "last_name"),
    "email": ("contact", "email"),
    "phone": ("contact", "phone"),
    "company_name": ("company", "name"),
    "notes": ("intent", "notes"),
    "last_contact_at": ("engagement", "last_contact_at"),
    "lead_score": ("ai", "lead_score"),
    "sentiment": ("ai", "sentiment"),
    "ai_summary": ("ai", "summary"),
    "recommended_action": ("ai", "recommended_action"),
}


@dataclass(frozen=True)
class ContactHistory:
    """Engagement facts from the source, used only to derive creation activities."""

    preferred_channel: Channel | None
    contact_attempts: int
    replied: bool


@dataclass(frozen=True)
class AdaptedLead:
    data: LeadImportData
    raw_payload: dict[str, Any]
    history: ContactHistory


class LeadAdapter(ABC):
    @abstractmethod
    async def parse(self, record: dict[str, Any]) -> AdaptedLead:
        """Map one raw record; raises ``pydantic.ValidationError`` (convert with ``record_errors``)."""


class _RawSections(BaseModel):
    """Structural check only: nested sections must be objects (or null/absent). Everything else is ignored."""

    model_config = ConfigDict(extra="ignore")

    contact: dict[str, Any] | None = None
    company: dict[str, Any] | None = None
    intent: dict[str, Any] | None = None
    engagement: dict[str, Any] | None = None
    ai: dict[str, Any] | None = None


class JsonLeadAdapter(LeadAdapter):
    """Records shaped like ``docs/files/sample_raw_leads.json``. Unmapped keys survive only in ``raw_payload``."""

    async def parse(self, record: dict[str, Any]) -> AdaptedLead:
        sections = _RawSections.model_validate(record)
        data = LeadImportData.model_validate(_flatten(record, sections))
        return AdaptedLead(data=data, raw_payload=copy.deepcopy(record), history=_history(sections))


def _flatten(record: dict[str, Any], sections: _RawSections) -> dict[str, Any]:
    contact = sections.contact or {}
    engagement = sections.engagement or {}
    ai = sections.ai or {}
    custom_fields = record.get("custom_fields")
    return {
        "external_id": record.get("lead_id"),
        "source": record.get("source"),
        "status": record.get("status"),
        "priority": record.get("priority"),
        "created_at": record.get("created_at"),
        "first_name": contact.get("first_name"),
        "last_name": contact.get("last_name"),
        "email": contact.get("email"),
        "phone": contact.get("phone"),
        "company_name": (sections.company or {}).get("name"),
        "notes": (sections.intent or {}).get("notes"),
        "last_contact_at": engagement.get("last_contact_at"),
        "lead_score": ai.get("lead_score"),
        "sentiment": ai.get("sentiment"),
        "ai_summary": ai.get("summary"),
        "recommended_action": ai.get("recommended_action"),
        "custom_fields": {} if custom_fields is None else custom_fields,
    }


def _history(sections: _RawSections) -> ContactHistory:
    """Lenient by design: malformed engagement metadata degrades to defaults instead of failing the record."""
    contact = sections.contact or {}
    engagement = sections.engagement or {}
    channel = contact.get("preferred_channel")
    attempts = engagement.get("contact_attempts")
    replied = engagement.get("replied")
    return ContactHistory(
        preferred_channel=_CHANNEL_ALIASES.get(channel.strip().lower()) if isinstance(channel, str) else None,
        contact_attempts=attempts if _is_count(attempts) else 0,
        replied=replied if isinstance(replied, bool) else False,
    )


def _is_count(value: object) -> TypeIs[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def record_errors(exc: ValidationError) -> list[RecordError]:
    """Adapter validation errors as ``RecordError``s located in the raw record (``["ai", "lead_score"]``)."""
    errors: list[RecordError] = []
    for error in exc.errors():
        loc: list[str | int] = list(error["loc"])
        if loc and isinstance(loc[0], str) and loc[0] in _RAW_LOCATIONS:
            loc = [*_RAW_LOCATIONS[loc[0]], *loc[1:]]
        errors.append(RecordError(loc=loc, msg=error["msg"], type=error["type"]))
    return errors

"""Test data builders for the platform suite. DB helpers flush (never commit) so tests control transactions."""

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ai.schemas.enums import ActivityType
from app.models import Activity, Business, Lead

SAMPLE_LEADS_PATH = Path(__file__).resolve().parents[2] / "docs" / "files" / "sample_raw_leads.json"


async def make_business(session: AsyncSession, slug: str = "acme", **fields: Any) -> Business:
    business = Business(name=slug.title(), slug=slug, **fields)
    session.add(business)
    await session.flush()
    return business


async def make_lead(session: AsyncSession, business: Business, **fields: Any) -> Lead:
    lead = Lead(business_id=business.id, **({"source": "website"} | fields))
    session.add(lead)
    await session.flush()
    return lead


async def make_activity(session: AsyncSession, lead: Lead, **fields: Any) -> Activity:
    defaults: dict[str, Any] = {"activity_type": ActivityType.LEAD_CREATED, "description": "test activity"}
    activity = Activity(business_id=lead.business_id, lead_id=lead.id, **(defaults | fields))
    session.add(activity)
    await session.flush()
    return activity


@cache
def _sample_text() -> str:
    return SAMPLE_LEADS_PATH.read_text(encoding="utf-8")


def load_sample() -> dict[str, Any]:
    """A fresh (mutable) copy of ``docs/files/sample_raw_leads.json``."""
    sample: dict[str, Any] = json.loads(_sample_text())
    return sample


def raw_lead(index: int = 0, **overrides: Any) -> dict[str, Any]:
    """A sample-shaped raw record (``leads[index]``, default lead_001) with top-level keys overridden."""
    record: dict[str, Any] = copy.deepcopy(load_sample()["leads"][index])
    return record | overrides

"""Test data builders for the platform suite: rows are inserted straight into the test Supabase project."""

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from supabase import AsyncClient

from ai.schemas.enums import ActivityType
from app.core.supabase import to_json
from app.models import Activity, Business, Lead

SAMPLE_LEADS_PATH = Path(__file__).resolve().parents[2] / "docs" / "files" / "sample_raw_leads.json"


async def _insert(db: AsyncClient, table: str, values: dict[str, Any]) -> dict[str, Any]:
    response = await db.table(table).insert(to_json(values)).execute()
    row: dict[str, Any] = response.data[0]
    return row


async def make_business(db: AsyncClient, slug: str = "acme", **fields: Any) -> Business:
    return Business.model_validate(await _insert(db, "businesses", {"name": slug.title(), "slug": slug} | fields))


async def make_lead(db: AsyncClient, business: Business, **fields: Any) -> Lead:
    values = {"business_id": business.id, "source": "website"} | fields
    return Lead.model_validate(await _insert(db, "leads", values))


async def make_activity(db: AsyncClient, lead: Lead, **fields: Any) -> Activity:
    defaults: dict[str, Any] = {"activity_type": ActivityType.LEAD_CREATED, "description": "test activity"}
    values = {"business_id": lead.business_id, "lead_id": lead.id} | defaults | fields
    return Activity.model_validate(await _insert(db, "activities", values))


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

"""`db/*.sql` must match the Python side. No database needed: the SQL files themselves are parsed.

The Python enums are the source of truth for enum columns. A new enum member without the matching CHECK change in
`db/*.sql` would pass every Python test and then fail at insert with a CHECK violation (a 500). Likewise a model
field without a column (or the reverse) would fail on every read or write.
"""

import re
from enum import StrEnum

import pytest
from pydantic import BaseModel

from ai.schemas.enums import ActivityType, Channel, Priority, Sentiment
from app.models import (
    Activity,
    AnalysisJob,
    AnalysisJobStatus,
    AnalysisTrigger,
    Business,
    DecisionChannel,
    IngestEvent,
    IngestStatus,
    Lead,
    ReplyDraft,
    ReplyDraftStatus,
    User,
    WhatsAppAccount,
)
from tests.platform.conftest import ROOT

SQL = "\n".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "db").glob("*.sql")))
ENUM_COLUMN_LENGTH = 32
USER_ROLES = {"owner", "manager", "sales", "admin"}

ENUM_CHECKS = [
    ("ck_leads_lead_priority", {member.value for member in Priority}),
    ("ck_leads_lead_sentiment", {member.value for member in Sentiment}),
    ("ck_activities_activity_type", {member.value for member in ActivityType}),
    ("ck_activities_activity_channel", {member.value for member in Channel}),
    ("ck_users_user_role", USER_ROLES),
    ("ck_analysis_jobs_analysis_job_status", {member.value for member in AnalysisJobStatus}),
    ("ck_analysis_jobs_analysis_trigger", {member.value for member in AnalysisTrigger}),
    ("ck_ingest_events_ingest_status", {member.value for member in IngestStatus}),
    ("ck_reply_drafts_reply_draft_status", {member.value for member in ReplyDraftStatus}),
    ("ck_reply_drafts_reply_channel", {member.value for member in Channel}),
    ("ck_reply_drafts_decision_channel", {member.value for member in DecisionChannel}),
]


def _check_values(constraint: str) -> set[str]:
    match = re.search(rf"CONSTRAINT {constraint} CHECK \(\w+ IN \((.*?)\)\)", SQL, re.DOTALL)
    assert match, f"{constraint} not found in db/*.sql"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _table_columns(table: str) -> set[str]:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", SQL, re.DOTALL)
    assert match, f"table {table} not found in db/*.sql"
    lines = (line.strip() for line in match.group(1).splitlines())
    return {line.split()[0] for line in lines if line and not line.startswith(("CONSTRAINT", "FOREIGN", "'", ")"))}


@pytest.mark.parametrize(("constraint", "values"), ENUM_CHECKS)
def test_check_constraint_allows_exactly_the_enum_values(constraint: str, values: set[str]) -> None:
    assert _check_values(constraint) == values


@pytest.mark.parametrize(
    "enum",
    [
        Priority, Sentiment, ActivityType, Channel, AnalysisJobStatus, AnalysisTrigger, IngestStatus, ReplyDraftStatus,
        DecisionChannel,
    ],
)
def test_enum_values_fit_the_column(enum: type[StrEnum]) -> None:
    assert all(len(member.value) <= ENUM_COLUMN_LENGTH for member in enum)


@pytest.mark.parametrize(
    ("table", "model"), [
        ("businesses", Business),
        ("leads", Lead),
        ("activities", Activity),
        ("users", User),
        ("analysis_jobs", AnalysisJob),
        ("whatsapp_accounts", WhatsAppAccount),
        ("ingest_events", IngestEvent),
        ("reply_drafts", ReplyDraft),
    ]
)
def test_table_columns_match_the_model(table: str, model: type[BaseModel]) -> None:
    assert _table_columns(table) == set(model.model_fields)

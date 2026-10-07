"""`ai.schemas.enums` is the source of truth for enum columns; the migrated CHECK constraints must match it.

A new enum member without a migration would pass every Python test and then fail at flush with a CHECK
violation (a 500). These tests catch that drift against the real migrated schema.
"""

import re
from enum import StrEnum

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai.schemas.enums import ActivityType, Channel, Priority, Sentiment

# Mirrors `str_enum(..., length=32)` in app/models/base.py.
ENUM_COLUMN_LENGTH = 32

ENUM_COLUMNS = [
    ("leads", "priority", Priority, "ck_leads_lead_priority"),
    ("leads", "sentiment", Sentiment, "ck_leads_lead_sentiment"),
    ("activities", "activity_type", ActivityType, "ck_activities_activity_type"),
    ("activities", "channel", Channel, "ck_activities_activity_channel"),
]

_CHECK_CONSTRAINTS = text(
    """
    SELECT con.conname, pg_get_constraintdef(con.oid)
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = ANY (con.conkey)
    WHERE con.contype = 'c' AND rel.relname = :table AND att.attname = :column
    """
)
_LITERAL = re.compile(r"'([^']+)'::character varying")


@pytest.mark.parametrize(("table", "column", "enum", "constraint"), ENUM_COLUMNS)
async def test_check_constraint_allows_exactly_the_enum_values(
    session: AsyncSession, table: str, column: str, enum: type[StrEnum], constraint: str
) -> None:
    rows = (await session.execute(_CHECK_CONSTRAINTS, {"table": table, "column": column})).tuples().all()

    assert [name for name, _ in rows] == [constraint]
    [(_, definition)] = rows
    assert set(_LITERAL.findall(definition)) == {member.value for member in enum}


@pytest.mark.parametrize("enum", [Priority, Sentiment, ActivityType, Channel])
def test_enum_values_fit_the_column(enum: type[StrEnum]) -> None:
    assert all(len(member.value) <= ENUM_COLUMN_LENGTH for member in enum)

import uuid
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import RecordError

MAX_IMPORT_RECORDS = 1000


class ImportEnvelope(BaseModel):
    """``POST /leads/import`` body, shaped like ``docs/files/sample_raw_leads.json``.

    Records stay untyped here: each one is validated by the ingestion adapter so a bad record fails alone
    instead of rejecting the whole batch.
    """

    model_config = ConfigDict(extra="forbid")

    dataset: str | None = Field(default=None, max_length=100)
    schema_version: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=500)
    leads: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_IMPORT_RECORDS)


class ImportOutcome(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    FAILED = "failed"


class ImportRecordResult(BaseModel):
    """Result for the record at ``index``; ``lead_id`` is null only when failed, ``errors`` only when failed."""

    index: int
    external_id: str | None
    outcome: ImportOutcome
    lead_id: uuid.UUID | None = None
    errors: list[RecordError] | None = None


class ImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    failed: int
    results: list[ImportRecordResult]

    @classmethod
    def from_results(cls, results: list[ImportRecordResult]) -> Self:
        def count(outcome: ImportOutcome) -> int:
            return sum(1 for result in results if result.outcome is outcome)

        return cls(
            created=count(ImportOutcome.CREATED),
            updated=count(ImportOutcome.UPDATED),
            skipped=count(ImportOutcome.SKIPPED),
            failed=count(ImportOutcome.FAILED),
            results=results,
        )

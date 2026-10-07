import json
from typing import Any

from pydantic import BaseModel

# Cap for free-form JSON accepted from clients (serialized UTF-8 bytes).
MAX_JSON_FIELD_BYTES = 64 * 1024


def json_size(value: Any) -> int:
    """Compact serialized UTF-8 size of a JSON-compatible value."""
    return len(json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str).encode())


def check_json_size(value: Any, field: str, limit: int = MAX_JSON_FIELD_BYTES) -> Any:
    """Return ``value`` unchanged, or raise ``ValueError`` when it serializes to more than ``limit`` bytes."""
    size = json_size(value)
    if size > limit:
        raise ValueError(f"{field} exceeds {limit} bytes when serialized ({size})")
    return value


class Page[T](BaseModel):
    """One page of a list endpoint: ``total`` counts every match, ``items`` holds at most ``limit`` of them."""

    items: list[T]
    total: int
    limit: int
    offset: int


class RecordError(BaseModel):
    """One validation problem, shaped like FastAPI's 422 ``details`` entries."""

    loc: list[str | int]
    msg: str
    type: str

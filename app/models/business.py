from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Business(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant. Per-business behaviour lives in JSONB, never in per-customer columns (MAIN_PLAN §4)."""

    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    industry: Mapped[str | None] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")

    configuration: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    custom_field_definitions: Mapped[list[dict[str, Any]]] = mapped_column(default=list, server_default="[]")
    ai_configuration: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")

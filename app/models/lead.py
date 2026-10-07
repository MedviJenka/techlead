import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ai.schemas.enums import Priority, Sentiment
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum

DEFAULT_LEAD_STATUS = "new"


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Normalized lead (MAIN_PLAN §5). Business-specific data goes to `custom_fields`."""

    __tablename__ = "leads"
    __table_args__ = (
        # Target of the composite FK from activities: an activity can only reference a lead of its own business.
        UniqueConstraint("business_id", "id"),
        CheckConstraint("lead_score BETWEEN 0 AND 100", name="lead_score_range"),
        Index(
            "uq_leads_business_id_source_external_id",
            "business_id",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index("ix_leads_business_id_created_at", "business_id", "created_at"),
        Index("ix_leads_business_id_status", "business_id", "status"),
        Index("ix_leads_business_id_email", "business_id", "email"),
        Index("ix_leads_business_id_phone", "business_id", "phone"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(50))
    # Free-form because every business defines its own pipeline statuses (MAIN_PLAN §52).
    status: Mapped[str] = mapped_column(String(50), default=DEFAULT_LEAD_STATUS, server_default=DEFAULT_LEAD_STATUS)
    priority: Mapped[Priority | None] = mapped_column(str_enum(Priority, "lead_priority"))

    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    company_name: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

    lead_score: Mapped[int | None] = mapped_column(Integer)
    sentiment: Mapped[Sentiment | None] = mapped_column(str_enum(Sentiment, "lead_sentiment"))
    ai_summary: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(String(50))

    custom_fields: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")

    last_contact_at: Mapped[datetime | None]

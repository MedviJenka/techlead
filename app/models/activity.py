import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from ai.schemas.enums import ActivityType, Channel
from app.models.base import Base, UUIDPrimaryKeyMixin, str_enum


class Activity(UUIDPrimaryKeyMixin, Base):
    """Append-only lead event (MAIN_PLAN §6). History is context for agents, so rows are never updated."""

    __tablename__ = "activities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "lead_id"],
            ["leads.business_id", "leads.id"],
            ondelete="CASCADE",
        ),
        Index("ix_activities_business_id_lead_id_created_at", "business_id", "lead_id", "created_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"))
    lead_id: Mapped[uuid.UUID]
    activity_type: Mapped[ActivityType] = mapped_column(str_enum(ActivityType, "activity_type"))
    channel: Mapped[Channel | None] = mapped_column(str_enum(Channel, "activity_channel"))
    description: Mapped[str] = mapped_column(Text)
    # `metadata` is reserved on declarative classes, hence the attribute/column name split.
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

"""core platform tables

Revision ID: dac288e936a6
Revises:
Create Date: 2026-10-07 18:15:15.534650
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dac288e936a6"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "custom_field_definitions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "ai_configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_businesses")),
        sa.UniqueConstraint("slug", name=op.f("uq_businesses_slug")),
    )
    op.create_table(
        "leads",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="new", nullable=False),
        sa.Column(
            "priority",
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="lead_priority",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("lead_score", sa.Integer(), nullable=True),
        sa.Column(
            "sentiment",
            sa.Enum(
                "negative",
                "neutral",
                "mixed",
                "positive",
                name="lead_sentiment",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("recommended_action", sa.String(length=50), nullable=True),
        sa.Column(
            "custom_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("last_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("lead_score BETWEEN 0 AND 100", name=op.f("ck_leads_lead_score_range")),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_leads_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
        sa.UniqueConstraint("business_id", "id", name=op.f("uq_leads_business_id_id")),
    )
    op.create_index(
        "ix_leads_business_id_created_at",
        "leads",
        ["business_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_leads_business_id_email", "leads", ["business_id", "email"], unique=False)
    op.create_index("ix_leads_business_id_phone", "leads", ["business_id", "phone"], unique=False)
    op.create_index("ix_leads_business_id_status", "leads", ["business_id", "status"], unique=False)
    op.create_index(
        "uq_leads_business_id_source_external_id",
        "leads",
        ["business_id", "source", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.create_table(
        "activities",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column(
            "activity_type",
            sa.Enum(
                "lead_created",
                "lead_updated",
                "email_sent",
                "email_received",
                "whatsapp_sent",
                "whatsapp_received",
                "phone_call",
                "status_changed",
                "score_changed",
                "proposal_sent",
                "meeting_scheduled",
                "ai_analysis",
                "followup_created",
                name="activity_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.Enum(
                "whatsapp",
                "email",
                "sms",
                "phone",
                "crm_task",
                name="activity_channel",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id", "lead_id"],
            ["leads.business_id", "leads.id"],
            name=op.f("fk_activities_business_id_lead_id_leads"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_activities_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activities")),
    )
    op.create_index(
        "ix_activities_business_id_lead_id_created_at",
        "activities",
        ["business_id", "lead_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_activities_business_id_lead_id_created_at", table_name="activities")
    op.drop_table("activities")
    op.drop_index(
        "uq_leads_business_id_source_external_id",
        table_name="leads",
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.drop_index("ix_leads_business_id_status", table_name="leads")
    op.drop_index("ix_leads_business_id_phone", table_name="leads")
    op.drop_index("ix_leads_business_id_email", table_name="leads")
    op.drop_index("ix_leads_business_id_created_at", table_name="leads")
    op.drop_table("leads")
    op.drop_table("businesses")

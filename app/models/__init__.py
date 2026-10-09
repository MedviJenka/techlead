"""Typed rows of the Supabase tables. The tables themselves are defined in `db/*.sql`; keep both in sync."""

from app.models.activity import Activity
from app.models.analysis_job import AnalysisJob, AnalysisJobStatus, AnalysisTrigger
from app.models.business import Business
from app.models.ingest_event import IngestEvent, IngestStatus
from app.models.lead import Lead
from app.models.reply_draft import DecisionChannel, ReplyDraft, ReplyDraftStatus
from app.models.user import User
from app.models.whatsapp_account import WhatsAppAccount

__all__ = [
    "Activity",
    "AnalysisJob",
    "AnalysisJobStatus",
    "AnalysisTrigger",
    "Business",
    "DecisionChannel",
    "IngestEvent",
    "IngestStatus",
    "Lead",
    "ReplyDraft",
    "ReplyDraftStatus",
    "User",
    "WhatsAppAccount",
]

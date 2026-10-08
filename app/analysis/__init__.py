"""Bridge from the application to the CrewAI layer (`ai/`): snapshots in, recommendations out."""

from app.analysis.engine import AnalysisEngine, CrewAnalysisEngine
from app.analysis.read_service import SingleLeadReadService
from app.analysis.snapshots import to_activity_snapshot, to_business_profile, to_lead_snapshot

__all__ = [
    "AnalysisEngine",
    "CrewAnalysisEngine",
    "SingleLeadReadService",
    "to_activity_snapshot",
    "to_business_profile",
    "to_lead_snapshot",
]

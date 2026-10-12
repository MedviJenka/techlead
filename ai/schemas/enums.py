from enum import IntEnum, StrEnum


class Priority(StrEnum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class IntentLevel(StrEnum):
    NONE   = "none"
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class Urgency(StrEnum):
    UNKNOWN   = "unknown"
    LOW       = "low"
    MEDIUM    = "medium"
    HIGH      = "high"
    IMMEDIATE = "immediate"


class FitLevel(StrEnum):
    UNKNOWN   = "unknown"
    POOR      = "poor"
    PARTIAL   = "partial"
    GOOD      = "good"
    EXCELLENT = "excellent"


class Sentiment(StrEnum):
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    POSITIVE = "positive"


class NextAction(StrEnum):
    CALL = "call"
    SEND_WHATSAPP = "send_whatsapp"
    SEND_EMAIL = "send_email"
    REQUEST_INFORMATION = "request_information"
    SCHEDULE_DEMO = "schedule_demo"
    SEND_PROPOSAL = "send_proposal"
    WAIT = "wait"
    NURTURE = "nurture"
    CLOSE_LOST = "close_lost"
    ESCALATE_TO_MANAGER = "escalate_to_manager"


class Channel(StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"
    PHONE = "phone"
    CRM_TASK = "crm_task"


class ActivityType(StrEnum):
    LEAD_CREATED = "lead_created"
    LEAD_UPDATED = "lead_updated"
    EMAIL_SENT = "email_sent"
    EMAIL_RECEIVED = "email_received"
    WHATSAPP_SENT = "whatsapp_sent"
    WHATSAPP_RECEIVED = "whatsapp_received"
    PHONE_CALL = "phone_call"
    STATUS_CHANGED = "status_changed"
    SCORE_CHANGED = "score_changed"
    PROPOSAL_SENT = "proposal_sent"
    MEETING_SCHEDULED = "meeting_scheduled"
    AI_ANALYSIS = "ai_analysis"
    FOLLOWUP_CREATED = "followup_created"


class AutonomyLevel(IntEnum):
    RECOMMEND_ONLY = 0
    DRAFT_ONLY = 1
    LOW_RISK_AUTOMATION = 2
    AUTOMATED = 3


class ModelTier(StrEnum):
    """Which class of LLM an agent needs (see MAIN_PLAN §57 cost management)."""

    FAST = "fast"
    REASONING = "reasoning"

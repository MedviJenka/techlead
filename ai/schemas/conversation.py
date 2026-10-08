from datetime import datetime

from pydantic import BaseModel, Field

from ai.schemas.enums import IntentLevel, Sentiment


class ExtractedField(BaseModel):
    """A proposed lead-field update. The application validates before persisting."""

    name: str = Field(description="Lead or custom-field name, snake_case")
    value: str = Field(description="Value exactly as stated or clearly implied by the customer")
    confidence: float = Field(ge=0, le=1)


class ConversationAnalysis(BaseModel):
    """Structured understanding of an inbound message (MAIN_PLAN §21)."""

    intent: str = Field(description="What the customer wants, in one sentence")
    purchase_intent: IntentLevel
    sentiment: Sentiment
    buying_signals: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    requested_actions: list[str] = Field(default_factory=list)
    decision_dependency: str | None = Field(default=None, description="e.g. 'partner approval'")
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    followup_date: datetime | None = Field(default=None, description="Follow-up time the customer asked for, if any")

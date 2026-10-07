"""Checks on customer-facing drafts: no invented pricing, discounts or completed-action claims."""

import re

from ai.guardrails.base import Guardrail, Validator, as_guardrail
from ai.schemas import AutonomyLevel, BusinessProfile, Channel, FollowupDraft, LeadSnapshot

MAX_LENGTH: dict[Channel, int] = {Channel.SMS: 320, Channel.WHATSAPP: 1000, Channel.EMAIL: 3000}

_AMOUNT = re.compile(
    r"(?:[₪$€£]\s?(?P<pre>\d[\d,.]*))|(?:(?P<post>\d[\d,.]*)\s?(?:₪|ils\b|nis\b|usd\b|eur\b|shekels?\b|dollars?\b))",
    re.IGNORECASE,
)
_DISCOUNT = re.compile(
    r"\b(?:discount\w*|coupon|promo(?:tion)?\s+code|special\s+(?:offer|price)|\d+\s?%\s?off)\b|הנחה",
    re.IGNORECASE,
)
_COMPLETED_CLAIM = re.compile(
    r"\b(?:I|we)(?:'ve|\s+have)\s+(?:already\s+)?(?:sent|scheduled|booked|reserved|approved|processed|arranged|completed)\b"
    r"|\b(?:has|have)\s+been\s+(?:sent|scheduled|booked|approved|processed|confirmed)\b",
    re.IGNORECASE,
)


def make_messaging_validator(business: BusinessProfile, lead: LeadSnapshot) -> Validator[FollowupDraft]:
    known_amounts = {_digits(str(int(lead.budget)))} if lead.budget is not None else set()
    approval_mandatory = business.ai.autonomy_level < AutonomyLevel.LOW_RISK_AUTOMATION

    def validate(draft: FollowupDraft) -> list[str]:
        errors: list[str] = []
        limit = MAX_LENGTH.get(draft.channel)
        if limit is not None and len(draft.message) > limit:
            errors.append(f"{draft.channel} messages must be at most {limit} characters (got {len(draft.message)}).")
        if draft.channel == Channel.EMAIL and not (draft.subject or "").strip():
            errors.append("Email drafts need a subject.")
        invented = [m.group(0) for m in _AMOUNT.finditer(draft.message) if _amount_digits(m) not in known_amounts]
        if invented:
            errors.append(f"Do not state prices or amounts that are not in the lead data: {invented}.")
        if _DISCOUNT.search(draft.message):
            errors.append("Do not offer or mention discounts or promotions.")
        if _COMPLETED_CLAIM.search(draft.message):
            errors.append("Do not claim that an action was already completed; this is a draft awaiting approval.")
        if approval_mandatory and not draft.requires_human_approval:
            errors.append("This business requires human approval for every outbound message; set requires_human_approval=true.")
        return errors

    return validate


def make_messaging_guardrail(business: BusinessProfile, lead: LeadSnapshot) -> Guardrail:
    return as_guardrail(FollowupDraft, make_messaging_validator(business, lead))


def _amount_digits(match: re.Match[str]) -> str:
    raw = match.group("pre") or match.group("post") or ""
    return _digits(re.sub(r"[.,]\d{1,2}$", "", raw))  # drop cents: "90,000.00" -> "90000"


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)

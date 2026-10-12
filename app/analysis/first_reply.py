"""The first reply (MAIN_PLAN §66): a lead that wrote on WhatsApp gets a drafted answer within a minute, sent to the
owner's phone for approval. Runs in the worker as the last step of NewLeadFlow, after the lead is scored.

With auto-send on (``WhatsAppAccount.auto_send_after_minutes``), the draft also gets an ``auto_send_at``: the worker
sends it then if the owner has not decided. Not for a lead the analysis found a poor fit: that draft waits for the
owner.
"""

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from ai.schemas import Channel, NextActionRecommendation, QualificationResult
from ai.schemas.enums import ActivityType, FitLevel
from app.analysis.drafting import ReplyDrafter
from app.analysis.snapshots import to_activity_snapshot, to_business_profile, to_lead_snapshot
from app.core.logger import Logger
from app.intelligence.facts import OUTBOUND_TYPES
from app.models import ReplyDraft
from app.services.lead import LeadService
from app.services.replies import ReplyService

logger = Logger("first-reply")


class FirstReply:
    def __init__(
        self, leads: LeadService, replies: ReplyService, drafter: ReplyDrafter, clock: Callable[[], datetime]
    ) -> None:
        self._leads = leads
        self._replies = replies
        self._drafter = drafter
        self._clock = clock

    async def run(
        self,
        business_id: uuid.UUID,
        lead_id: uuid.UUID,
        recommendation: NextActionRecommendation | None,
        qualification: QualificationResult | None = None,
    ) -> ReplyDraft | None:
        """The draft sent for approval, or None when the lead needs none (already answered, not on WhatsApp...)."""
        log: dict[str, Any] = {"business_id": str(business_id), "lead_id": str(lead_id)}
        account = await self._replies.accounts.get(business_id)
        if account is None:
            logger.fire("first_reply_skipped", reason="whatsapp_not_connected", **log)
            return None
        business, lead, activities = await self._leads.analysis_inputs(business_id, lead_id)
        inbound = [a for a in activities if a.activity_type is ActivityType.WHATSAPP_RECEIVED]
        if not inbound or lead.phone is None:
            logger.fire("first_reply_skipped", reason="no_whatsapp_message", **log)
            return None
        if any(a.activity_type in OUTBOUND_TYPES for a in activities):
            logger.fire("first_reply_skipped", reason="already_answered", **log)
            return None
        if await self._replies.drafts.for_lead(business_id, lead_id):
            logger.fire("first_reply_skipped", reason="already_drafted", **log)  # e.g. a retried job
            return None
        draft = await self._drafter.draft(
            to_business_profile(business),
            to_lead_snapshot(lead, activities),
            [to_activity_snapshot(activity) for activity in activities],
            recommendation,
        )
        auto_send_at = None
        if account.auto_send_after_minutes is not None and not (qualification and qualification.fit is FitLevel.POOR):
            auto_send_at = self._clock() + timedelta(minutes=account.auto_send_after_minutes)
        saved = await self._replies.create_draft(
            business_id, lead_id, Channel.WHATSAPP, draft.message, draft.objective, auto_send_at
        )
        if saved is None:
            logger.fire("first_reply_skipped", reason="already_drafted", **log)
            return None
        seconds = round((self._clock() - lead.created_at).total_seconds(), 1)
        logger.fire(
            "first_reply_drafted", draft_id=str(saved.id), seconds_since_lead=seconds,
            auto_send_at=auto_send_at.isoformat() if auto_send_at else None, **log,
        )
        body = inbound[-1].metadata.get("body")
        await self._replies.request_approval(account, saved, lead, body if isinstance(body, str) else None)
        return saved

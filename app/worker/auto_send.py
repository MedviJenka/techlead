"""Auto-send (MAIN_PLAN §66): the worker sends first replies the owner did not decide on by their ``auto_send_at``.

A sweep every few seconds, beside the job loop. Sending goes through ``ReplyService.auto_send``, a conditional claim
like the owner's own Approve: whichever comes first wins, and a draft the owner is editing is never sent. Several
workers may sweep at once for the same reason.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from app.core.logger import Logger
from app.models import ReplyDraft
from app.services.replies import ReplyService

logger = Logger("auto-send")

BATCH = 20


class DueDrafts(Protocol):
    async def due_for_auto_send(self, now: datetime, limit: int) -> list[ReplyDraft]: ...


class AutoSender:
    """``make_replies(now)`` builds the reply service for one sweep, with that sweep's time as its clock."""

    def __init__(
        self, drafts: DueDrafts, make_replies: Callable[[datetime], ReplyService], clock: Callable[[], datetime]
    ) -> None:
        self._drafts = drafts
        self._make_replies = make_replies
        self._clock = clock

    async def run_once(self) -> int:
        """Send every due draft (up to ``BATCH``). The number sent."""
        now = self._clock()
        due = await self._drafts.due_for_auto_send(now, BATCH)
        if not due:
            return 0
        replies = self._make_replies(now)
        sent = 0
        for draft in due:
            try:
                if await replies.auto_send(draft) is not None:
                    sent += 1
            except Exception as exc:  # one broken draft must not stop the others
                logger.fire(
                    "reply_auto_send_failed", level="error", _exc_info=exc, business_id=str(draft.business_id),
                    draft_id=str(draft.id),
                )
        logger.fire("auto_send_sweep", due=len(due), sent=sent)
        return sent

    async def run(self, stop: asyncio.Event, interval_seconds: float = 15.0) -> None:
        """Sweep until ``stop`` is set. A database outage skips sweeps, never ends the loop."""
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception as exc:
                logger.fire("auto_send_loop_error", level="error", _exc_info=exc)
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except TimeoutError:
                pass

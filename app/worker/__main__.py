"""``python -m app.worker``: run the AI worker until SIGINT/SIGTERM. Needs the CrewAI dependencies (worker image).

Two loops: analysis jobs (``AnalysisWorker``) and the auto-send sweep for undecided first replies (``AutoSender``).

Run as many workers as you like: each claims its own jobs (``claim_analysis_job`` uses SKIP LOCKED).
"""

import asyncio
import signal
import sys
from datetime import datetime

from app.analysis import CrewAnalysisEngine, missing_ai_configuration, reasoning_model
from app.analysis.cost import TokenPrices
from app.analysis.drafting import CrewReplyDrafter
from app.analysis.first_reply import FirstReply
from app.analysis.flow import NewLeadFlow
from app.core.clock import utc_now
from app.core.locks import PROCESS_ID
from app.core.logger import Logger, configure_logging
from app.core.supabase import get_supabase
from app.repositories import ReplyDraftRepository
from app.repositories.analysis_job import AnalysisJobRepository
from app.services.lead import LeadService
from app.services.replies import ApprovalTemplate, ReplyService, whatsapp_sender
from app.worker.auto_send import AutoSender
from app.worker.runner import AnalysisWorker
from settings import get_config

logger = Logger("worker")


async def main() -> int:
    configure_logging()
    config = get_config()
    if problem := missing_ai_configuration(config):
        logger.fire("worker_not_configured", level="error", reason=problem)
        return 2
    db = await get_supabase()
    engine, drafter = CrewAnalysisEngine(), CrewReplyDrafter()
    model, prices = reasoning_model(config), TokenPrices.from_settings(config)
    sender, template = whatsapp_sender(config), ApprovalTemplate.from_settings(config)

    def make_replies(now: datetime) -> ReplyService:
        return ReplyService(db, LeadService(db, now), sender, template, now)

    def make_flow(now: datetime) -> NewLeadFlow:
        replies = make_replies(now)
        return NewLeadFlow(replies.leads, engine, model, prices, FirstReply(replies.leads, replies, drafter, utc_now))

    worker = AnalysisWorker(AnalysisJobRepository(db), make_flow, utc_now, name=f"worker:{PROCESS_ID}")
    auto_sender = AutoSender(ReplyDraftRepository(db), make_replies, utc_now)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows: Ctrl+C raises KeyboardInterrupt instead
            pass
    await asyncio.gather(worker.run(stop), auto_sender.run(stop))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)

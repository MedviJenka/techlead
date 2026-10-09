"""Public webhooks: no user session. Each one authenticates the sender itself (here: Meta's signature)."""

import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import WhatsAppInboxDep
from app.channels.whatsapp import verify_signature
from app.core.errors import ForbiddenError, ServiceUnavailableError, UnauthorizedError
from app.core.logger import Logger
from settings import get_config

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = Logger(__name__)

WHATSAPP_PATH = "/webhooks/whatsapp"


@router.get("/whatsapp", response_class=PlainTextResponse)
async def verify_whatsapp_webhook(
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge", max_length=200)] = None,
) -> str:
    """Meta's subscription handshake: echo ``hub.challenge`` when ``hub.verify_token`` is ours."""
    expected = get_config().WHATSAPP_VERIFY_TOKEN
    if mode == "subscribe" and expected and token and challenge and hmac.compare_digest(token, expected):
        logger.fire("whatsapp_webhook_verified")
        return challenge
    logger.fire("whatsapp_webhook_verification_refused", level="warning", mode=mode)
    raise ForbiddenError("Webhook verification failed")


@router.post("/whatsapp")
async def receive_whatsapp_webhook(request: Request, inbox: WhatsAppInboxDep) -> dict[str, str]:
    """Inbound messages. Answered with an error when a message failed, so Meta redelivers the event."""
    secret = get_config().WHATSAPP_APP_SECRET
    if not secret:
        raise ServiceUnavailableError("The WhatsApp webhook is not configured: set WHATSAPP_APP_SECRET")
    body = await request.body()
    if not verify_signature(secret, body, request.headers.get("X-Hub-Signature-256")):
        logger.fire("whatsapp_webhook_bad_signature", level="warning")
        raise UnauthorizedError("Invalid webhook signature")
    try:
        payload = json.loads(body)
    except ValueError:
        logger.fire("whatsapp_webhook_not_json", level="warning")
        return {"status": "ignored"}
    await inbox.handle(payload)
    return {"status": "ok"}

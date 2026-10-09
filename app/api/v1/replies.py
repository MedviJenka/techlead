import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import ReplyServiceDep
from app.api.v1.webhooks import WHATSAPP_PATH
from app.models import DecisionChannel, ReplyDraft
from app.schemas.reply import (
    ReplyApproval,
    ReplyDraftRead,
    WhatsAppConnection,
    WhatsAppConnectionRead,
    WhatsAppStatus,
)
from settings import get_config

router = APIRouter(prefix="/businesses/{business_id}", tags=["replies"])


def _read(draft: ReplyDraft) -> ReplyDraftRead:
    return ReplyDraftRead.model_validate(draft.model_dump())


@router.get("/whatsapp", response_model=WhatsAppStatus)
async def whatsapp_status(business_id: uuid.UUID, service: ReplyServiceDep) -> WhatsAppStatus:
    config = get_config()
    account = await service.account(business_id)
    return WhatsAppStatus(
        connection=WhatsAppConnectionRead.model_validate(account.model_dump()) if account else None,
        configured=bool(config.WHATSAPP_ACCESS_TOKEN and config.WHATSAPP_APP_SECRET and config.WHATSAPP_VERIFY_TOKEN),
        webhook_path=f"{config.api_prefix}{WHATSAPP_PATH}",
    )


@router.put("/whatsapp", response_model=WhatsAppConnectionRead)
async def connect_whatsapp(
    business_id: uuid.UUID, payload: WhatsAppConnection, service: ReplyServiceDep
) -> WhatsAppConnectionRead:
    account = await service.connect(business_id, payload)
    return WhatsAppConnectionRead.model_validate(account.model_dump())


@router.delete("/whatsapp", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_whatsapp(business_id: uuid.UUID, service: ReplyServiceDep) -> None:
    await service.disconnect(business_id)


@router.get("/replies", response_model=list[ReplyDraftRead])
async def pending_replies(
    business_id: uuid.UUID, service: ReplyServiceDep, limit: Annotated[int, Query(ge=1, le=100)] = 25
) -> list[ReplyDraftRead]:
    """Drafts waiting for a decision (or whose sending failed), newest first: the dashboard's approval queue."""
    return [_read(draft) for draft in await service.pending(business_id, limit)]


@router.get("/leads/{lead_id}/replies", response_model=list[ReplyDraftRead])
async def lead_replies(business_id: uuid.UUID, lead_id: uuid.UUID, service: ReplyServiceDep) -> list[ReplyDraftRead]:
    return [_read(draft) for draft in await service.for_lead(business_id, lead_id)]


@router.post("/replies/{draft_id}/approve", response_model=ReplyDraftRead)
async def approve_reply(
    business_id: uuid.UUID, draft_id: uuid.UUID, payload: ReplyApproval, service: ReplyServiceDep
) -> ReplyDraftRead:
    """Send the draft, or ``message`` instead of it, to the lead on WhatsApp."""
    return _read(await service.approve(business_id, draft_id, DecisionChannel.DASHBOARD, payload.message))


@router.post("/replies/{draft_id}/reject", response_model=ReplyDraftRead)
async def reject_reply(business_id: uuid.UUID, draft_id: uuid.UUID, service: ReplyServiceDep) -> ReplyDraftRead:
    return _read(await service.reject(business_id, draft_id, DecisionChannel.DASHBOARD))

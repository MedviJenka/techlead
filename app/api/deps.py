import uuid
from datetime import datetime
from typing import Annotated

from fastapi import Depends
from supabase import AsyncClient

from app.core.auth import CurrentUser
from app.core.clock import utc_now
from app.core.supabase import get_supabase
from app.repositories import BusinessRepository
from app.services import BusinessService
from app.services.account import AccountService
from app.services.dashboard import DashboardService
from app.services.inbox import WhatsAppInbox
from app.services.lead import LeadService
from app.services.replies import ApprovalTemplate, ReplyService, whatsapp_sender
from settings import get_config

SupabaseDep = Annotated[AsyncClient, Depends(get_supabase)]


def get_business_service(db: SupabaseDep) -> BusinessService:
    return BusinessService(BusinessRepository(db))


BusinessServiceDep = Annotated[BusinessService, Depends(get_business_service)]


def get_account_service(db: SupabaseDep) -> AccountService:
    return AccountService(db)


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]


async def require_business_access(business_id: uuid.UUID, user: CurrentUser, service: AccountServiceDep) -> None:
    """Dependency of every ``/businesses/{business_id}`` route: the caller must belong to that business."""
    await service.require_access(user, business_id)


def get_lead_service(db: SupabaseDep, now: Annotated[datetime, Depends(utc_now)]) -> LeadService:
    return LeadService(db, now)


def get_dashboard_service(db: SupabaseDep) -> DashboardService:
    return DashboardService(db)


LeadServiceDep = Annotated[LeadService, Depends(get_lead_service)]
DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]



def get_reply_service(
    db: SupabaseDep, leads: LeadServiceDep, now: Annotated[datetime, Depends(utc_now)]
) -> ReplyService:
    config = get_config()
    return ReplyService(db, leads, whatsapp_sender(config), ApprovalTemplate.from_settings(config), now)


ReplyServiceDep = Annotated[ReplyService, Depends(get_reply_service)]


def get_whatsapp_inbox(db: SupabaseDep, leads: LeadServiceDep, replies: ReplyServiceDep) -> WhatsAppInbox:
    return WhatsAppInbox(db, leads, replies)


WhatsAppInboxDep = Annotated[WhatsAppInbox, Depends(get_whatsapp_inbox)]

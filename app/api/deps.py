import uuid
from datetime import datetime
from typing import Annotated

from fastapi import Depends
from supabase import AsyncClient

from app.analysis import AnalysisEngine, CrewAnalysisEngine
from app.core.auth import CurrentUser
from app.core.clock import utc_now
from app.core.errors import ServiceUnavailableError
from app.core.supabase import get_supabase
from app.repositories import BusinessRepository
from app.services import BusinessService
from app.services.account import AccountService
from app.services.dashboard import DashboardService
from app.services.lead import LeadService
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


def get_analysis_engine() -> AnalysisEngine:
    """The CrewAI engine. OpenAI models (the default provider) need ``OPENAI_API_KEY``; tests override this."""
    config = get_config()
    model = config.AI_REASONING_MODEL or config.OPENAI_MODEL
    if (model.startswith("openai/") or "/" not in model) and not config.OPENAI_API_KEY:
        raise ServiceUnavailableError("AI analysis is not configured: set OPENAI_API_KEY")
    return CrewAnalysisEngine()


AnalysisEngineDep = Annotated[AnalysisEngine, Depends(get_analysis_engine)]

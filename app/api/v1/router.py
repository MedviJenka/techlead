from fastapi import APIRouter, Depends

from app.api.deps import require_business_access
from app.api.v1 import businesses, health, leads, me
from app.core.auth import current_user


def build_router(prefix: str) -> APIRouter:
    """Mount the v1 endpoints under ``prefix`` (``Settings.api_prefix``); built per app, never at import time.

    Everything except ``/health`` requires a signed-in user; business-scoped routes also require membership.
    """
    router = APIRouter(prefix=prefix)
    router.include_router(health.router)
    signed_in = [Depends(current_user)]
    router.include_router(me.router, dependencies=signed_in)
    router.include_router(businesses.router, dependencies=signed_in)
    router.include_router(leads.router, dependencies=[*signed_in, Depends(require_business_access)])
    return router

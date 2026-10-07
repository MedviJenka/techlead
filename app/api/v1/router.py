from fastapi import APIRouter

from app.api.v1 import businesses, health


def build_router(prefix: str) -> APIRouter:
    """Mount the v1 endpoints under ``prefix`` (``Settings.api_prefix``); built per app, never at import time."""
    router = APIRouter(prefix=prefix)
    router.include_router(health.router)
    router.include_router(businesses.router)
    return router

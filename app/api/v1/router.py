from settings import Config
from fastapi import APIRouter
from app.api.v1 import businesses, health


api_router = APIRouter(prefix=f"/api/{Config.API_VERSION}")
api_router.include_router(health.router)
api_router.include_router(businesses.router)

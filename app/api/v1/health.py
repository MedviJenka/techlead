import logging

from fastapi import APIRouter, Response, status
from httpx import HTTPError
from postgrest.exceptions import APIError

from app.api.deps import SupabaseDep
from app.schemas import HealthStatus

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthStatus)
async def health(db: SupabaseDep, response: Response) -> HealthStatus:
    try:
        await db.table("businesses").select("id").limit(1).execute()
    except (APIError, HTTPError, OSError):
        logger.warning("health_database_unavailable", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthStatus(status="degraded", database="unavailable")
    return HealthStatus(status="ok", database="ok")

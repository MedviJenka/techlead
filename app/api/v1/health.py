import logging
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.api.deps import SessionDep
from app.schemas import HealthStatus

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthStatus)
async def health(session: SessionDep, response: Response) -> HealthStatus:
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError):
        logger.warning("health_database_unavailable", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthStatus(status="degraded", database="unavailable")
    return HealthStatus(status="ok", database="ok")

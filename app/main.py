from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import build_router
from app.core.errors import register_exception_handlers
from app.core.logger import Logger, configure_logging
from settings import get_config

logger = Logger(__name__)


def create_app() -> FastAPI:
    config = get_config()
    configure_logging()
    app = FastAPI(title="Techlead", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(build_router(config.api_prefix))
    logger.fire("app_started", env=config.APP_ENV, api_prefix=config.api_prefix)
    return app


app = create_app()

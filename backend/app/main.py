from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import get_settings
from app.observability.otel import init_tracing


def create_app() -> FastAPI:
    settings = get_settings()
    init_tracing()

    app = FastAPI(title=settings.APP_NAME)
    app.include_router(health_router, prefix="/api")

    return app


app = create_app()

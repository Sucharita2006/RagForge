from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.documents import router as documents_router
from app.api.eval import router as eval_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.query import router as query_router
from app.api.retrieve import router as retrieve_router
from app.config import get_settings
from app.observability.otel import init_tracing


def create_app() -> FastAPI:
    settings = get_settings()
    init_tracing()

    app = FastAPI(title=settings.APP_NAME)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.ENV == "local" else [],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(ingest_router, prefix="/api")
    app.include_router(documents_router, prefix="/api")
    app.include_router(query_router, prefix="/api")
    app.include_router(retrieve_router, prefix="/api")
    app.include_router(eval_router, prefix="/api")

    return app


app = create_app()

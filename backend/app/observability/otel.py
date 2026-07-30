from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider

from app.config import get_settings

_initialized = False


def init_tracing() -> None:
    """Set up the OTel SDK tracer provider.

    Span *exporting* to Postgres (SPEC.md §3.8) is wired up in Phase 5;
    until then this just gives every module a working `trace.get_tracer(__name__)`.
    """
    global _initialized
    if _initialized:
        return
    settings = get_settings()
    resource = Resource.create({SERVICE_NAME: settings.APP_NAME})
    trace.set_tracer_provider(TracerProvider(resource=resource))
    _initialized = True

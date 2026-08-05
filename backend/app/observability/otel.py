from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import get_settings

_initialized = False


def init_tracing() -> None:
    """Set up the OTel SDK tracer provider and, when enabled, the Postgres
    span exporter that backs the Traces viewer and Analytics page
    (SPEC.md §3.8).

    Export is batched off the request thread by BatchSpanProcessor, so a
    slow or failing write never adds latency to the query it describes.
    """
    global _initialized
    if _initialized:
        return
    settings = get_settings()
    resource = Resource.create({SERVICE_NAME: settings.APP_NAME})
    provider = TracerProvider(resource=resource)

    if settings.SPAN_EXPORT_ENABLED and settings.OTEL_EXPORTER == "postgres":
        # imported lazily: pulls in SQLAlchemy sync-engine machinery that a
        # tracing-only consumer (e.g. a unit test) has no reason to load.
        from app.observability.exporter import PostgresSpanExporter

        provider.add_span_processor(BatchSpanProcessor(PostgresSpanExporter()))

    trace.set_tracer_provider(provider)
    _initialized = True

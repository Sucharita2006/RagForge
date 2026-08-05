import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models.spans import Span

logger = logging.getLogger(__name__)

_OPENINFERENCE_KIND_ATTR = "openinference.span.kind"


def _sync_database_url() -> str:
    """The app's DATABASE_URL is asyncpg; this exporter needs a *sync* driver.

    OTel's SpanExporter.export() is a synchronous method invoked from
    BatchSpanProcessor's own background thread. Reaching into the app's
    async engine from there would mean driving an event loop from a
    non-async thread - the same class of bug as the MissingGreenlet crash
    in Phase 4 (DECISIONS.md 2026-08-04). A separate, small sync engine on
    psycopg (already a dependency) keeps the two execution models fully
    separate instead of bridging them.
    """
    return get_settings().DATABASE_URL.replace("+asyncpg", "+psycopg")


class PostgresSpanExporter(SpanExporter):
    """Persists OpenInference spans to the `spans` table (SPEC.md §3.8).

    Engine/session are created lazily on first export so that merely
    importing this module (e.g. in a unit test) never opens a connection
    pool.
    """

    def __init__(self) -> None:
        self._session_factory: sessionmaker[Session] | None = None

    def _sessions(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            # pool_size=1: this exporter is driven by a single background
            # thread, so a larger pool would just hold idle connections.
            engine = create_engine(_sync_database_url(), pool_size=1, max_overflow=1)
            self._session_factory = sessionmaker(engine)
        return self._session_factory

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            rows = [row for row in (self._to_row(span) for span in spans) if row is not None]
        except Exception:
            logger.exception("failed to convert spans for export")
            return SpanExportResult.FAILURE
        if not rows:
            return SpanExportResult.SUCCESS

        try:
            with self._sessions()() as session:
                session.add_all(rows)
                session.commit()
        except Exception:
            # Telemetry must never take down the request path it observes;
            # a failed export is logged and dropped, not retried forever.
            logger.exception("failed to persist %d spans", len(rows))
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    @staticmethod
    def _to_row(span: ReadableSpan) -> Span | None:
        context = span.get_span_context()
        if context is None:
            # a span with no context can't be correlated to a trace, which is
            # the whole point of persisting it - drop rather than store an orphan
            return None
        attributes = dict(span.attributes or {})
        kind = str(attributes.pop(_OPENINFERENCE_KIND_ATTR, "INTERNAL"))

        # OTel timestamps are epoch nanoseconds; None only for a span that
        # was never ended, which BatchSpanProcessor shouldn't hand us.
        start_ns = span.start_time or 0
        end_ns = span.end_time or start_ns

        return Span(
            id=uuid.uuid4(),
            span_id=format(context.span_id, "016x"),
            trace_id=format(context.trace_id, "032x"),
            parent_span_id=format(span.parent.span_id, "016x") if span.parent else None,
            kind=kind,
            name=span.name,
            started_at=datetime.fromtimestamp(start_ns / 1e9, tz=UTC),
            ended_at=datetime.fromtimestamp(end_ns / 1e9, tz=UTC),
            latency_ms=int((end_ns - start_ns) / 1e6),
            attributes=attributes,
            status=span.status.status_code.name if span.status else "UNSET",
        )

    def shutdown(self) -> None:
        if self._session_factory is not None:
            self._session_factory.kw["bind"].dispose()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True

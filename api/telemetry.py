import logging
import sys

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator
from pythonjsonlogger import jsonlogger

from config import settings


def setup_logging() -> None:
    """
    Structured JSON logging — every log line is a parseable JSON object.
    Loki can index the fields (level, service, trace_id) without
    parsing free-form text.
    """
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def setup_tracing(app) -> None:
    """
    Auto-instrumentation: FastAPI, SQLAlchemy, and Redis all emit
    spans automatically. You get a trace of every request showing
    exactly how much time was spent in each layer.
    """
    resource = Resource.create({
        "service.name": "linkvault-api",
        "service.version": "0.1.0",
        "deployment.environment": settings.app_env,
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint="http://otel-collector:4317",
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # These patch the libraries so every DB query and Redis call
    # automatically becomes a child span in the current trace
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
    FastAPIInstrumentor.instrument_app(app)


def setup_metrics(app) -> None:
    """
    Prometheus metrics: request count, latency histogram, in-flight requests.
    Exposed at GET /metrics — Prometheus scrapes this endpoint.
    """
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app)
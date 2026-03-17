"""
Lightweight OpenTelemetry tracing.
When OTEL_EXPORTER_OTLP_ENDPOINT is set, creates spans around key operations.

Usage:
    from agents.otel_callbacks import traced

    with traced("analysis.agent.finint", {"conflict": conflict}):
        result = run_finint_agent(conflict)
"""

import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

_tracer = None
_otel_enabled = None


def _is_otel_enabled() -> bool:
    global _otel_enabled
    if _otel_enabled is None:
        _otel_enabled = bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())
    return _otel_enabled


def init_otel() -> None:
    """Initialize OpenTelemetry TracerProvider with OTLP gRPC exporter. No-op if OTEL_EXPORTER_OTLP_ENDPOINT not set."""
    global _tracer
    if not _is_otel_enabled():
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        if endpoint.startswith("https://"):
            endpoint = endpoint[len("https://") :]
        elif endpoint.startswith("http://"):
            endpoint = endpoint[len("http://") :]
        if not endpoint:
            return
        service_name = os.getenv("OTEL_SERVICE_NAME", "digital-war-room")
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("digital-war-room", "1.0.0")
    except Exception:
        _tracer = None


@contextmanager
def traced(name: str, attributes: Optional[Dict[str, Any]] = None):
    """Context manager that creates an OTEL span. No-op when OTEL is not configured."""
    if _tracer is None:
        yield None
        return
    try:
        from opentelemetry.trace import StatusCode
    except ImportError:
        yield None
        return

    span = _tracer.start_span(name)
    if attributes:
        for k, v in attributes.items():
            if v is not None:
                span.set_attribute(k, str(v) if not isinstance(v, (int, float, bool)) else v)
    start = time.perf_counter()
    try:
        yield span
        span.set_attribute("duration_ms", (time.perf_counter() - start) * 1000)
        span.set_status(StatusCode.OK)
    except Exception as e:
        span.set_attribute("duration_ms", (time.perf_counter() - start) * 1000)
        span.set_status(StatusCode.ERROR, str(e))
        span.record_exception(e)
        raise
    finally:
        span.end()

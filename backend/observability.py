"""
Observability stack: structured logging (structlog), tracing (OpenTelemetry), error tracking (Sentry).

Usage:
    from observability import get_logger, run_agent_traced, run_node_traced, init

    init()  # call once at app startup (e.g. in main.py lifespan)

    logger = get_logger()
    logger.info("event_name", key=value, ...)

    result = run_agent_traced("finint", conflict, lambda: run_finint_agent(conflict))

    # In DAG: run_node_traced(node_id, node_type, conflict, lambda: executor(store))
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Structlog
# ---------------------------------------------------------------------------

_logger: Optional[Any] = None  # structlog.BoundLogger | None


def _configure_structlog() -> None:
    """Configure structlog: JSON in production, console in development."""
    import structlog

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    is_prod = os.getenv("ENV", os.getenv("ENVIRONMENT", "")).lower() in ("production", "prod")
    if is_prod:
        shared_processors.append(structlog.processors.format_exc_info)
        processors = shared_processors + [structlog.processors.JSONRenderer()]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
        ]
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _configure_stdlib_bridge() -> None:
    """Route standard library logging to structlog so logging.getLogger() calls emit structured logs."""
    import structlog

    try:
        from structlog.stdlib import ProcessorFormatter, add_log_level, add_logger_name
    except ImportError:
        return
    is_prod = os.getenv("ENV", os.getenv("ENVIRONMENT", "")).lower() in ("production", "prod")
    shared = [
        add_log_level,
        add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    formatter = ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
            if not is_prod
            else structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def get_logger(name: str = "") -> Any:
    """Return a structlog logger. Call after init()."""
    import structlog

    if name:
        return structlog.get_logger(name)
    return structlog.get_logger()


# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------


def _init_sentry() -> None:
    """Initialize Sentry when SENTRY_DSN is set (e.g. Free Tier for Open Source)."""
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", os.getenv("ENV", "development")),
            release=os.getenv("SENTRY_RELEASE", ""),  # e.g. git SHA
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0")),
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
            send_default_pii=False,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tracing (OpenTelemetry) – delegates to existing otel_callbacks
# ---------------------------------------------------------------------------


def _get_traced() -> Any:
    from agents.otel_callbacks import traced

    return traced


# ---------------------------------------------------------------------------
# Agent / node helpers
# ---------------------------------------------------------------------------


def run_agent_traced(agent_name: str, query: str, run_fn: Callable[[], T]) -> T:
    """
    Run agent logic inside an OTEL span and structured logs (agent_start, agent_complete).

    query: typically the conflict name; used for span attribute and query_length in logs.
    run_fn: callable that returns the agent result; may include tokens_used or usage.total_tokens.
    """
    traced = _get_traced()
    log = get_logger(__name__)
    log.info("agent_start", agent=agent_name, query_length=len(query) if query else 0)
    with traced(f"agent.{agent_name}", {"conflict": query or None}):
        result = run_fn()
    tokens_used = None
    if isinstance(result, dict):
        tokens_used = result.get("tokens_used")
        if tokens_used is None and isinstance(result.get("usage"), dict):
            tokens_used = result.get("usage", {}).get("total_tokens")
    log.info("agent_complete", agent=agent_name, tokens_used=tokens_used)
    return result


def run_node_traced(
    node_id: str,
    node_type: str,
    conflict: str,
    run_fn: Callable[[], T],
) -> T:
    """
    Run a DAG node inside an OTEL span and structured logs (node_start, node_complete).
    Use in DAG scheduler when executing a node.
    """
    traced = _get_traced()
    log = get_logger(__name__)
    log.info("node_start", node_id=node_id, node_type=node_type, conflict=conflict)
    with traced(f"dag.node.{node_id}", {"conflict": conflict, "node_type": node_type}):
        result = run_fn()
    log.info("node_complete", node_id=node_id, node_type=node_type, conflict=conflict)
    return result


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


def init() -> None:
    """
    Initialize observability: structlog, Sentry, OpenTelemetry.
    Call once at application startup (e.g. FastAPI lifespan).
    """
    _configure_structlog()
    _configure_stdlib_bridge()
    _init_sentry()
    from agents.otel_callbacks import init_otel

    init_otel()

# Observability Stack

Structured logging, tracing, and error tracking for production-ready operation.

## Built-in

- **structlog** – Structured logging (JSON in production, readable console in development). Use `observability.get_logger()` and log with key-value pairs: `logger.info("event_name", agent=name, query_length=len(q))`. Standard library `logging.getLogger()` calls are bridged to structlog after `init()` so all logs use the same format.
- **OpenTelemetry** – When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, spans are created for full analysis and per-DAG node. Existing `agents.otel_callbacks.traced()` is used; DAG scheduler wraps each node with `observability.run_node_traced()`.
- **Sentry** – When `SENTRY_DSN` is set, errors and performance transactions are sent to Sentry (e.g. [Free Tier for Open Source](https://sentry.io)). `logging.error` / `logging.exception` are also sent as Sentry events via LoggingIntegration.

## Health endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness: process is up. |
| `GET /health/ready` | Readiness: if `DATABASE_URL` is set, checks DB connectivity; returns 503 when DB is unreachable. |
| `GET /api/agents/health` | Per-source health from HealthRegistry: availability %, latency, circuit_open, last_error. |

## Usage

```python
from observability import get_logger, run_agent_traced, init

init()  # called once at app startup (main.py lifespan)

logger = get_logger()
logger.info("agent_start", agent="finint", query_length=len(conflict))

result = run_agent_traced("finint", conflict, lambda: run_finint_agent(conflict))
```

DAG node execution is automatically wrapped with `run_node_traced` (node_start / node_complete + span `dag.node.<node_id>`).

## Optional tools

- **Better Stack** (Logtail) / **Axiom** – For log aggregation: send structlog JSON to their OTLP or HTTP ingest. Often used with the same `OTEL_EXPORTER_OTLP_ENDPOINT` for traces; logs can be shipped via a sidecar or their agent.
- **PostHog** – User/product analytics (session replay, feature flags). Frontend integration; backend can send events via PostHog API if needed. Complements Vercel Analytics with more control and self-hosting options.

## Env (see backend/.env.example)

| Variable | Purpose |
|----------|---------|
| `ENV` / `ENVIRONMENT` | `production` → structlog JSON; else console |
| `SENTRY_DSN` | Enable Sentry error tracking |
| `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE` | Sentry context |
| `SENTRY_TRACES_SAMPLE_RATE` | 0–1, default 0.1 |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP gRPC endpoint for traces |
| `OTEL_SERVICE_NAME` | Service name in traces, default `digital-war-room` |

import logging
import os
import asyncio
import uuid
from collections import deque
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()
# Ensure backend/.env is loaded when running from project root (e.g. uvicorn backend.main:app)
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.gzip import GZipMiddleware

from middleware.rate_limit import limiter
from middleware.tenant_context import TenantContextMiddleware
from api.routes import router as api_router
from api.pdf_export import router as pdf_router
from api.greynoise import router as greynoise_router
from agents.config import CORS_ORIGINS
from observability import init as init_observability
from services.job_queue import JobQueue
from services.http_client import close_http_client
from services.startup_tasks import start_startup_tasks, stop_startup_tasks
from services.state_service import StateService
from services.tenant_auth import build_request_context
from agents.socmint_agent import scrape_twitter_nitter, scrape_telegram_channels, search_reddit


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[WebSocket, tuple[str, uuid.UUID]] = {}

    async def connect(self, websocket: WebSocket, *, conflict: str, tenant_id: uuid.UUID):
        await websocket.accept()
        self.active_connections[websocket] = (conflict, tenant_id)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.pop(websocket, None)

    async def broadcast(self, data: dict, *, conflict: str, tenant_id: uuid.UUID):
        dead: list[WebSocket] = []
        for connection, (ws_conflict, ws_tenant_id) in self.active_connections.items():
            if ws_conflict != conflict or ws_tenant_id != tenant_id:
                continue
            try:
                await connection.send_json(data)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.active_connections.pop(connection, None)


async def _resolve_ws_context(websocket: WebSocket):
    auth = websocket.headers.get("authorization")
    x_key = websocket.headers.get("x-api-key")
    x_tenant = websocket.headers.get("x-tenant-id") or websocket.query_params.get("tenant_id")
    return await build_request_context(
        authorization=auth,
        x_api_key=x_key,
        x_tenant_id=x_tenant,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_observability()  # structlog, Sentry, OpenTelemetry (OTEL when OTEL_EXPORTER_OTLP_ENDPOINT set)
    try:
        from services.schema_bootstrap import bootstrap_schema

        await bootstrap_schema()
    except Exception as e:
        logger.warning("Schema bootstrap skipped or failed: %s", e)
    app.state.state_service = StateService()
    # Legacy in-memory fallback when routes don't use state_service (e.g. tests)
    app.state.analysis_cache = {}
    app.state.analysis_last_error = {}
    app.state.analysis_inflight = {}
    app.state.escalation_timeline_history = {}
    app.state.agent_status_last = {}
    app.state.analysis_run_history = deque(maxlen=50)
    app.state.job_queue = JobQueue()
    app.state.ws_manager = ConnectionManager()
    startup_tasks = start_startup_tasks(app, logger)

    yield

    await stop_startup_tasks(startup_tasks)
    await close_http_client()


app = FastAPI(title="Conflict Analysis Backend", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantContextMiddleware)
if "*" in CORS_ORIGINS and os.getenv("ENVIRONMENT", "").lower() == "production":
    logger.warning(
        "CORS is set to '*' in production. Set CORS_ORIGINS to explicit origins (e.g. https://yourdomain.com)."
    )

app.include_router(api_router, prefix="/api")
app.include_router(pdf_router, prefix="/api")
app.include_router(greynoise_router, prefix="/api")


@app.get("/health")
def health() -> dict:
    """Liveness: process is up. Use /health/ready for readiness (includes optional DB check)."""
    return {"status": "ok"}


def _check_llm_status() -> dict:
    """Non-blocking probe: checks API key presence and attempts a minimal LLM call."""
    from agents.llm import _get_provider, require_api_key, call_llm, get_model_name

    provider = _get_provider()
    try:
        require_api_key()
    except RuntimeError as e:
        return {"provider": provider, "status": "no_api_key", "error": str(e)}

    try:
        call_llm(system="Reply with OK", user_content="health check", model=get_model_name("agent"), max_tokens=4)
        return {"provider": provider, "status": "ok"}
    except Exception as e:
        err = str(e).lower()
        if any(k in err for k in ("credit balance", "insufficient_quota", "billing", "exceeded your current quota")):
            return {"provider": provider, "status": "credit_exhausted", "error": str(e)}
        return {"provider": provider, "status": "error", "error": str(e)}


@app.get("/health/ready")
async def health_ready():
    """
    Readiness: app is ready to serve. Checks DB (when configured) and LLM connectivity.
    Returns 200 when ready, 503 when DB is unreachable (only when DATABASE_URL is set).
    LLM status is informational and does not affect the HTTP status code.
    """
    result: dict = {"status": "ok"}
    http_status = 200

    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        result["database"] = "not_configured"
    else:
        try:
            import asyncpg

            conn = await asyncio.wait_for(asyncpg.connect(db_url), timeout=3.0)
            await conn.close()
            result["database"] = "connected"
        except Exception as e:
            logger.warning("Readiness DB check failed: %s", e)
            result["status"] = "degraded"
            result["database"] = "unreachable"
            http_status = 503

    try:
        llm_info = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _check_llm_status),
            timeout=8.0,
        )
    except asyncio.TimeoutError:
        llm_info = {"status": "timeout"}
    result["llm"] = llm_info

    if http_status != 200:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=http_status, content=result)
    return result


@app.get("/")
def root() -> dict:
    """
    Simple root endpoint so platform health checks against `/` return 200.
    Returns the same payload as `/health` for consistency.
    """
    return {"status": "ok", "service": "conflict-backend"}


@app.websocket("/ws/{conflict}")
async def websocket_endpoint(websocket: WebSocket, conflict: str):
    manager = websocket.app.state.ws_manager
    try:
        req_ctx = await _resolve_ws_context(websocket)
    except PermissionError as e:
        await websocket.accept()
        await websocket.send_json({"status": "error", "message": str(e) or "unauthorized", "conflict": conflict})
        await websocket.close(code=1008)
        return
    except Exception as e:
        logger.warning("WS context resolution failed: %s", e)
        await websocket.accept()
        await websocket.send_json({"status": "error", "message": "context_resolution_failed", "conflict": conflict})
        await websocket.close(code=1011)
        return

    await manager.connect(websocket, conflict=conflict, tenant_id=req_ctx.tenant_id)
    logger.info("WS client connected – conflict: %s", conflict)
    try:
        ws_tid = req_ctx.tenant_id
        # Sofort gecachtes Ergebnis senden (von Auto-Run oder letztem POST)
        entry = websocket.app.state.state_service.get_cache(conflict, tenant_id=ws_tid)
        if entry:
            result = {**entry["result"], "status": "ok", "conflict": conflict}
            await websocket.send_json(result)
        else:
            await websocket.send_json({"status": "analyzing", "conflict": conflict})

        while True:
            await asyncio.sleep(60)
            entry = websocket.app.state.state_service.get_cache(conflict, tenant_id=ws_tid)
            if entry:
                result = {**entry["result"], "status": "ok", "conflict": conflict}
                await websocket.send_json(result)
            else:
                await websocket.send_json({"status": "analyzing", "conflict": conflict})

    except WebSocketDisconnect:
        websocket.app.state.ws_manager.disconnect(websocket)
        logger.info("WS client disconnected – conflict: %s", conflict)
    except Exception as e:
        logger.exception("WS error: %s", e)
        try:
            await websocket.send_json({"status": "error", "message": str(e), "conflict": conflict})
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
        websocket.app.state.ws_manager.disconnect(websocket)


@app.websocket("/ws/social/{conflict}")
async def websocket_social_endpoint(websocket: WebSocket, conflict: str):
    try:
        await _resolve_ws_context(websocket)
    except PermissionError as e:
        await websocket.accept()
        await websocket.send_json({"status": "error", "message": str(e) or "unauthorized", "conflict": conflict})
        await websocket.close(code=1008)
        return
    except Exception as e:
        logger.warning("Social WS context resolution failed: %s", e)
        await websocket.accept()
        await websocket.send_json({"status": "error", "message": "context_resolution_failed", "conflict": conflict})
        await websocket.close(code=1011)
        return

    await websocket.accept()
    logger.info("Social WS client connected – conflict: %s", conflict)
    loop = asyncio.get_running_loop()

    async def _collect_live_social() -> dict:
        twitter_fut = loop.run_in_executor(None, lambda: scrape_twitter_nitter(conflict))
        telegram_fut = loop.run_in_executor(None, lambda: scrape_telegram_channels(conflict))
        reddit_fut = loop.run_in_executor(None, lambda: search_reddit(conflict, limit=12))
        twitter_raw, telegram_raw, reddit_raw = await asyncio.gather(
            twitter_fut, telegram_fut, reddit_fut, return_exceptions=True
        )

        def _sanitize(items):
            if isinstance(items, list):
                return [i for i in items if isinstance(i, dict) and "error" not in i]
            return []

        twitter_items = _sanitize(twitter_raw)
        telegram_items = _sanitize(telegram_raw)
        reddit_items = _sanitize(reddit_raw)

        def _sort_by_signal(items: list[dict], key: str = "sentiment_score", limit: int = 8) -> list[dict]:
            return sorted(items, key=lambda x: abs(float(x.get(key, 0) or 0)), reverse=True)[:limit]

        return {
            "status": "ok",
            "conflict": conflict,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "twitter": _sort_by_signal(twitter_items),
            "telegram": _sort_by_signal(telegram_items),
            "reddit": sorted(reddit_items, key=lambda x: int(x.get("upvotes", 0) or 0), reverse=True)[:8],
        }

    try:
        while True:
            payload = await _collect_live_social()
            await websocket.send_json(payload)
            await asyncio.sleep(45)
    except WebSocketDisconnect:
        logger.info("Social WS client disconnected – conflict: %s", conflict)
    except Exception as e:
        logger.exception("Social WS error: %s", e)
        try:
            await websocket.send_json({"status": "error", "message": str(e), "conflict": conflict})
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass

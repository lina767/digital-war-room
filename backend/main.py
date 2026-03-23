import logging
import os
import asyncio
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
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
from api.routes import router as api_router, push_escalation_timeline, push_agent_status, push_run_history
from api.pdf_export import router as pdf_router
from api.greynoise import router as greynoise_router
from agents.supervisor import analyze_conflict
from agents.pattern_anomalies import attach_pattern_flags
from agents.config import CORS_ORIGINS, GREYNOISE_API_KEY, GREYNOISE_SCHEDULER_INTERVAL_SEC
from observability import init as init_observability
from services.job_queue import JobQueue
from services.http_client import get_http_client, close_http_client
from services.state_service import StateService
from agents.socmint_agent import scrape_twitter_nitter, scrape_telegram_channels, search_reddit

# Konflikt, der periodisch automatisch analysiert wird (unabhängig von Aufrufen)
from agents.config import DEFAULT_CONFLICT

# Standard conflict for periodic analysis (default: Iran)
AUTO_ANALYZE_CONFLICT = os.getenv("AUTO_ANALYZE_CONFLICT", DEFAULT_CONFLICT)
# Default: 1x täglich (86400s). Override via env AUTO_ANALYZE_INTERVAL_SEC.
AUTO_ANALYZE_INTERVAL_SEC = int(os.getenv("AUTO_ANALYZE_INTERVAL_SEC", "86400"))  # 24 Stunden


class ConnectionManager:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, data: dict):
        dead: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                dead.append(connection)
        self.active_connections -= set(dead)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_observability()  # structlog, Sentry, OpenTelemetry (OTEL when OTEL_EXPORTER_OTLP_ENDPOINT set)
    app.state.state_service = StateService()
    # Legacy in-memory fallback when routes don't use state_service (e.g. tests)
    app.state.analysis_cache = {}
    app.state.analysis_last_error = {}
    app.state.escalation_timeline_history = {}
    app.state.agent_status_last = {}
    app.state.analysis_run_history = deque(maxlen=50)
    app.state.job_queue = JobQueue()
    app.state.ws_manager = ConnectionManager()

    # Defer ACLED download/parse to a background task so the ASGI server can bind and
    # pass platform healthchecks (Railway, etc.) immediately. refresh_acled_aggregated()
    # can block on network I/O for minutes when credentials are set and data is stale.
    async def _acled_startup_refresh() -> None:
        try:
            from services.acled_aggregated import refresh_acled_aggregated

            await asyncio.to_thread(refresh_acled_aggregated)
            logger.info("ACLED aggregated data checked/refreshed at startup")
        except Exception as e:
            logger.warning("ACLED aggregated startup refresh failed: %s", e)

    acled_task = asyncio.create_task(_acled_startup_refresh())

    async def run_periodic_analysis():
        loop = asyncio.get_running_loop()
        first_delay = 5
        await asyncio.sleep(first_delay)
        consecutive_failures = 0
        while True:
            try:
                # Reset Haiku per-run counters and warm up HF models
                try:
                    from services.haiku_service import reset_run_counters, log_run_stats

                    reset_run_counters()
                except Exception:
                    pass
                try:
                    from services.hf_service import warmup

                    await warmup()
                except Exception:
                    pass

                result = await loop.run_in_executor(None, lambda: analyze_conflict(AUTO_ANALYZE_CONFLICT))
                at_ts = time.time()
                attach_pattern_flags(app.state.state_service, AUTO_ANALYZE_CONFLICT, result)
                app.state.state_service.set_cache(AUTO_ANALYZE_CONFLICT, result, at_ts)
                app.state.state_service.pop_last_error(AUTO_ANALYZE_CONFLICT)
                push_escalation_timeline(app.state, AUTO_ANALYZE_CONFLICT, at_ts, result)
                push_agent_status(app.state, result)
                push_run_history(app.state, AUTO_ANALYZE_CONFLICT, at_ts, result)
                await app.state.ws_manager.broadcast({**result, "status": "ok", "conflict": AUTO_ANALYZE_CONFLICT})

                # Log Haiku usage stats for this run
                try:
                    log_run_stats()
                except Exception:
                    pass

                logger.info("Analysis for %s done.", AUTO_ANALYZE_CONFLICT)
                consecutive_failures = 0
                await asyncio.sleep(AUTO_ANALYZE_INTERVAL_SEC)
            except Exception as e:
                consecutive_failures += 1
                retry_delay = min(60 * (2 ** (consecutive_failures - 1)), AUTO_ANALYZE_INTERVAL_SEC)
                logger.warning(
                    "Analysis failed (attempt %d): %s. Retrying in %ds.", consecutive_failures, e, retry_delay
                )
                await asyncio.sleep(retry_delay)

    analysis_task = asyncio.create_task(run_periodic_analysis())
    worker_task = asyncio.create_task(app.state.job_queue.worker())

    # GreyNoise Emerging Threats scheduler (6h cycle + daily tag discovery)
    greynoise_task = None
    greynoise_discovery_task = None
    if GREYNOISE_API_KEY:

        async def run_greynoise_scheduler():
            from agents.greynoise_agent import run_greynoise_scheduler_cycle

            await asyncio.sleep(15)
            while True:
                try:
                    await run_greynoise_scheduler_cycle()
                    logger.info("GreyNoise scheduler cycle complete.")
                except Exception as e:
                    logger.warning("GreyNoise scheduler error: %s", e)
                await asyncio.sleep(GREYNOISE_SCHEDULER_INTERVAL_SEC)

        async def run_greynoise_tag_discovery():
            from agents.greynoise_agent import run_tag_discovery_cycle

            await asyncio.sleep(60)
            while True:
                try:
                    await run_tag_discovery_cycle()
                except Exception as e:
                    logger.warning("GreyNoise tag discovery error: %s", e)
                await asyncio.sleep(86400)  # once daily

        greynoise_task = asyncio.create_task(run_greynoise_scheduler())
        greynoise_discovery_task = asyncio.create_task(run_greynoise_tag_discovery())

    # Newsletter daily job: default 10:00 Europe/Berlin (CET/CEST); run analysis then send emails.
    # NEWSLETTER_IN_PROCESS_SCHEDULER=false when using only external cron (POST /api/newsletter/send-daily).
    newsletter_task = None
    if (os.getenv("RESEND_API_KEY") or "").strip() and (os.getenv("NEWSLETTER_FROM") or "").strip():
        try:
            from services.newsletter_sender import log_newsletter_deliverability_hints

            log_newsletter_deliverability_hints()
        except Exception:
            pass
        in_process = (os.getenv("NEWSLETTER_IN_PROCESS_SCHEDULER", "true") or "").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        if in_process:
            def _seconds_until_next_send() -> float:
                """
                Next run: default 10:00 in Europe/Berlin (CET/CEST). Override via
                NEWSLETTER_SEND_TIMEZONE, NEWSLETTER_SEND_HOUR, NEWSLETTER_SEND_MINUTE.
                Legacy: if NEWSLETTER_SEND_UTC_HOUR is set in the environment, use that UTC hour instead.
                """
                if "NEWSLETTER_SEND_UTC_HOUR" in os.environ:
                    try:
                        send_hour = int(os.getenv("NEWSLETTER_SEND_UTC_HOUR", "6"), 10)
                    except ValueError:
                        send_hour = 6
                    send_hour = max(0, min(23, send_hour))
                    now = datetime.now(timezone.utc)
                    next_run = now.replace(hour=send_hour, minute=0, second=0, microsecond=0)
                    if next_run <= now:
                        next_run = next_run + timedelta(days=1)
                    return max(60.0, (next_run - now).total_seconds())

                tz_name = (os.getenv("NEWSLETTER_SEND_TIMEZONE") or "Europe/Berlin").strip() or "Europe/Berlin"
                try:
                    tz = ZoneInfo(tz_name)
                except Exception:
                    logger.warning("Invalid NEWSLETTER_SEND_TIMEZONE=%r; using Europe/Berlin", tz_name)
                    tz = ZoneInfo("Europe/Berlin")
                try:
                    hour = int(os.getenv("NEWSLETTER_SEND_HOUR", "10"), 10)
                except ValueError:
                    hour = 10
                try:
                    minute = int(os.getenv("NEWSLETTER_SEND_MINUTE", "0"), 10)
                except ValueError:
                    minute = 0
                hour = max(0, min(23, hour))
                minute = max(0, min(59, minute))
                now = datetime.now(tz)
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run = next_run + timedelta(days=1)
                return max(60.0, (next_run - now).total_seconds())

            _first_delay = _seconds_until_next_send()
            if "NEWSLETTER_SEND_UTC_HOUR" in os.environ:
                logger.info(
                    "Newsletter in-process scheduler: NEWSLETTER_SEND_UTC_HOUR=%s (UTC); first run in %.0f s",
                    os.getenv("NEWSLETTER_SEND_UTC_HOUR"),
                    _first_delay,
                )
            else:
                _tz = (os.getenv("NEWSLETTER_SEND_TIMEZONE") or "Europe/Berlin").strip() or "Europe/Berlin"
                try:
                    _h = int(os.getenv("NEWSLETTER_SEND_HOUR", "10"), 10)
                except ValueError:
                    _h = 10
                try:
                    _m = int(os.getenv("NEWSLETTER_SEND_MINUTE", "0"), 10)
                except ValueError:
                    _m = 0
                _h = max(0, min(23, _h))
                _m = max(0, min(59, _m))
                logger.info(
                    "Newsletter in-process scheduler: daily send at %02d:%02d %s; first run in %.0f s",
                    _h,
                    _m,
                    _tz,
                    _first_delay,
                )

            async def _newsletter_loop():
                from api.routes_newsletter import run_daily_newsletter_job

                while True:
                    delay = _seconds_until_next_send()
                    await asyncio.sleep(delay)
                    try:
                        conflicts, sent, skipped_dup = await run_daily_newsletter_job(app.state)
                        if skipped_dup:
                            logger.info("Newsletter daily job: skipped (already completed today)")
                        elif conflicts or sent:
                            logger.info("Newsletter daily job: conflicts=%s sent=%d", conflicts, sent)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.warning("Newsletter daily job error: %s", e)

            newsletter_task = asyncio.create_task(_newsletter_loop())
        else:
            logger.info(
                "Newsletter in-process scheduler disabled (NEWSLETTER_IN_PROCESS_SCHEDULER=false); "
                "use cron for POST /api/newsletter/send-daily"
            )

    # Ensure shared HTTP client is created early (so DNS pools etc. warm up)
    get_http_client()

    yield

    tasks_to_cancel = [analysis_task, worker_task, acled_task]
    if greynoise_task:
        tasks_to_cancel.append(greynoise_task)
    if greynoise_discovery_task:
        tasks_to_cancel.append(greynoise_discovery_task)
    if newsletter_task:
        tasks_to_cancel.append(newsletter_task)
    for task in tasks_to_cancel:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

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


@app.get("/health/ready")
async def health_ready():
    """
    Readiness: app is ready to serve. If DATABASE_URL is set, checks DB connectivity.
    Returns 200 when ready, 503 when DB is unreachable (only when DATABASE_URL is set).
    """
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        return {"status": "ok", "database": "not_configured"}
    try:
        import asyncpg

        conn = await asyncio.wait_for(asyncpg.connect(db_url), timeout=3.0)
        await conn.close()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.warning("Readiness DB check failed: %s", e)
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "unreachable", "error": str(e)},
        )


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
    await manager.connect(websocket)
    logger.info("WS client connected – conflict: %s", conflict)
    try:
        # Sofort gecachtes Ergebnis senden (von Auto-Run oder letztem POST)
        entry = websocket.app.state.state_service.get_cache(conflict)
        if entry:
            result = {**entry["result"], "status": "ok"}
            await websocket.send_json(result)
        else:
            await websocket.send_json({"status": "analyzing", "conflict": conflict})

        while True:
            await asyncio.sleep(60)
            entry = websocket.app.state.state_service.get_cache(conflict)
            if entry:
                result = {**entry["result"], "status": "ok"}
                await websocket.send_json(result)
            else:
                await websocket.send_json({"status": "analyzing", "conflict": conflict})

    except WebSocketDisconnect:
        websocket.app.state.ws_manager.disconnect(websocket)
        logger.info("WS client disconnected – conflict: %s", conflict)
    except Exception as e:
        logger.exception("WS error: %s", e)
        try:
            await websocket.send_json({"status": "error", "message": str(e)})
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
        websocket.app.state.ws_manager.disconnect(websocket)


@app.websocket("/ws/social/{conflict}")
async def websocket_social_endpoint(websocket: WebSocket, conflict: str):
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

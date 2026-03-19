import logging
import os
import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()
# Ensure backend/.env is loaded when running from project root (e.g. uvicorn backend.main:app)
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from api.routes import router as api_router, push_escalation_timeline, push_agent_status, push_run_history
from api.pdf_export import router as pdf_router
from api.greynoise import router as greynoise_router
from agents.supervisor import analyze_conflict
from agents.config import CORS_ORIGINS, GREYNOISE_API_KEY, GREYNOISE_SCHEDULER_INTERVAL_SEC
from agents.otel_callbacks import init_otel
from services.job_queue import JobQueue
from services.http_client import get_http_client, close_http_client
from services.state_service import StateService

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
    init_otel()  # OpenTelemetry TracerProvider + OTLP exporter when OTEL_EXPORTER_OTLP_ENDPOINT set
    app.state.state_service = StateService()
    # Legacy in-memory fallback when routes don't use state_service (e.g. tests)
    app.state.analysis_cache = {}
    app.state.analysis_last_error = {}
    app.state.escalation_timeline_history = {}
    app.state.agent_status_last = {}
    app.state.analysis_run_history = deque(maxlen=50)
    app.state.job_queue = JobQueue()
    app.state.ws_manager = ConnectionManager()

    try:
        from services.acled_aggregated import refresh_acled_aggregated

        refresh_acled_aggregated()
        logger.info("ACLED aggregated data checked/refreshed at startup")
    except Exception as e:
        logger.warning("ACLED aggregated startup refresh failed: %s", e)

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
                state = getattr(app.state, "state_service", None)
                if state:
                    state.set_cache(AUTO_ANALYZE_CONFLICT, result, at_ts)
                    state.pop_last_error(AUTO_ANALYZE_CONFLICT)
                else:
                    app.state.analysis_cache[AUTO_ANALYZE_CONFLICT] = {"result": result, "at": at_ts}
                    app.state.analysis_last_error.pop(AUTO_ANALYZE_CONFLICT, None)
                push_escalation_timeline(app.state, AUTO_ANALYZE_CONFLICT, at_ts, result)
                push_agent_status(app.state, result)
                push_run_history(app.state, AUTO_ANALYZE_CONFLICT, at_ts, result)
                wm = getattr(app.state, "ws_manager", None)
                if wm:
                    await wm.broadcast({**result, "status": "ok", "conflict": AUTO_ANALYZE_CONFLICT})

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

    # Ensure shared HTTP client is created early (so DNS pools etc. warm up)
    get_http_client()

    yield

    tasks_to_cancel = [analysis_task, worker_task]
    if greynoise_task:
        tasks_to_cancel.append(greynoise_task)
    if greynoise_discovery_task:
        tasks_to_cancel.append(greynoise_discovery_task)
    for task in tasks_to_cancel:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    await close_http_client()


app = FastAPI(title="Conflict Analysis Backend", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(pdf_router, prefix="/api")
app.include_router(greynoise_router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


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
        state = getattr(app.state, "state_service", None)
        entry = state.get_cache(conflict) if state else getattr(app.state, "analysis_cache", {}).get(conflict)
        if entry:
            result = {**entry["result"], "status": "ok"}
            await websocket.send_json(result)
        else:
            await websocket.send_json({"status": "analyzing", "conflict": conflict})

        while True:
            await asyncio.sleep(60)
            entry = state.get_cache(conflict) if state else getattr(app.state, "analysis_cache", {}).get(conflict)
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

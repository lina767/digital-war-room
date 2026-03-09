import os
import asyncio
import time
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from api.routes import router as api_router
from api.pdf_export import router as pdf_router
from api.stripe_checkout import router as stripe_router
from agents.supervisor import analyze_conflict
from services.job_queue import JobQueue
from services.http_client import get_http_client, close_http_client

load_dotenv()

os.environ.setdefault("LANGCHAIN_TRACING_V2", os.getenv("LANGCHAIN_TRACING_V2", "true"))
os.environ.setdefault("LANGCHAIN_ENDPOINT", os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"))

# Konflikt, der alle 6 Stunden automatisch analysiert wird (unabhängig von Aufrufen)
# Standard: nur "Iran"
AUTO_ANALYZE_CONFLICT = os.getenv("AUTO_ANALYZE_CONFLICT", "Iran")
# Default: alle 6 Stunden (21600s). Override via env AUTO_ANALYZE_INTERVAL_SEC.
AUTO_ANALYZE_INTERVAL_SEC = int(os.getenv("AUTO_ANALYZE_INTERVAL_SEC", "21600"))  # 6 Stunden


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.analysis_cache = {}  # conflict -> {"result": {...}, "at": unix_ts}
    app.state.job_queue = JobQueue()

    async def run_periodic_analysis():
        loop = asyncio.get_running_loop()
        first_delay = 15  # Erste Analyse 15 s nach Start, dann alle AUTO_ANALYZE_INTERVAL_SEC
        await asyncio.sleep(first_delay)
        while True:
            try:
                result = await loop.run_in_executor(None, lambda: analyze_conflict(AUTO_ANALYZE_CONFLICT))
                app.state.analysis_cache[AUTO_ANALYZE_CONFLICT] = {"result": result, "at": time.time()}
                print(f"[periodic] Analysis for {AUTO_ANALYZE_CONFLICT} done.")
            except Exception as e:
                print(f"[periodic] Analysis failed: {e}")
            await asyncio.sleep(AUTO_ANALYZE_INTERVAL_SEC)

    analysis_task = asyncio.create_task(run_periodic_analysis())
    worker_task = asyncio.create_task(app.state.job_queue.worker())

    # Ensure shared HTTP client is created early (so DNS pools etc. warm up)
    get_http_client()

    yield

    for task in (analysis_task, worker_task):
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(pdf_router, prefix="/api")
app.include_router(stripe_router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ── WebSocket Manager ──────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.active_connections.remove(d)


manager = ConnectionManager()


@app.websocket("/ws/{conflict}")
async def websocket_endpoint(websocket: WebSocket, conflict: str):
    await manager.connect(websocket)
    print(f"[WS] Client connected – conflict: {conflict}")
    try:
        # Sofort gecachtes Ergebnis senden (von Auto-Run oder letztem POST)
        cache = getattr(app.state, "analysis_cache", {})
        entry = cache.get(conflict)
        if entry:
            result = {**entry["result"], "status": "ok"}
            await websocket.send_json(result)
        else:
            await websocket.send_json({"status": "analyzing", "conflict": conflict})

        # Alle 60 s gecachtes Ergebnis pushen (wird stündlich vom Hintergrund-Job aktualisiert)
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(60)
            cache = getattr(app.state, "analysis_cache", {})
            entry = cache.get(conflict)
            if entry:
                result = {**entry["result"], "status": "ok"}
                await websocket.send_json(result)
            else:
                await websocket.send_json({"status": "analyzing", "conflict": conflict})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print(f"[WS] Client disconnected – conflict: {conflict}")
    except Exception as e:
        print(f"[WS] Error: {e}")
        try:
            await websocket.send_json({"status": "error", "message": str(e)})
        except Exception:
            pass
        manager.disconnect(websocket)


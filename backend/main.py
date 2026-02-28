import os
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router
from api.pdf_export import router as pdf_router
from agents.supervisor import analyze_conflict

load_dotenv()

os.environ.setdefault("LANGCHAIN_TRACING_V2", os.getenv("LANGCHAIN_TRACING_V2", "true"))
os.environ.setdefault("LANGCHAIN_ENDPOINT", os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"))

app = FastAPI(title="Conflict Analysis Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(pdf_router, prefix="/api")


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
        # Send initial analysis immediately on connect
        await websocket.send_json({"status": "analyzing", "conflict": conflict})
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, analyze_conflict, conflict)
        result["status"] = "ok"
        await websocket.send_json(result)

        # Then push updates every 60 seconds
        while True:
            await asyncio.sleep(60)
            await websocket.send_json({"status": "analyzing", "conflict": conflict})
            result = await loop.run_in_executor(None, analyze_conflict, conflict)
            result["status"] = "ok"
            await websocket.send_json(result)

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


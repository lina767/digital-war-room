# API Reference

Backend REST endpoints. Base URL is the backend root (e.g. `https://your-railway-url.up.railway.app`). All listed paths under **Analysis**, **Agents**, **Proximity**, **Chokepoints**, **Compliance**, etc. are prefixed with `/api` (e.g. `GET /api/analyze/latest`).

Authentication: endpoints do not require auth unless noted. CORS is configured via `CORS_ORIGINS`; frontend must send requests to the backend URL set in `VITE_API_URL`.

---

## Health & Root

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check; returns `{"status": "ok"}`. |
| GET | `/` | Same as `/health`; returns `{"status": "ok", "service": "conflict-backend"}`. |

---

## Analysis

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/analyze/stream` | SSE stream: one event per agent as it completes, then a final supervisor event. Query: `conflict` (default `Iran`). |
| GET | `/api/analyze/latest` | Returns the last cached analysis for `conflict`. Query: `conflict` (default `Iran`). 404 if no cache. |
| GET | `/api/analyze/status` | Lightweight: whether cache exists, last update time, and last background run error. Query: `conflict`. |
| GET | `/api/analyze/timeline` | Escalation score over time for the conflict. Query: `conflict`. |
| POST | `/api/analyze` | Returns cached analysis only (same as GET latest). Body: `{"conflict": "Iran"}`. 503 if no cache. |
| GET | `/api/analyze/refresh` | Kicks off a full analysis in the background; returns immediately. Query: `conflict`, optional `sync=true` (blocking; may timeout). |
| POST | `/api/analyze/trigger` | Triggers a full analysis (optional secret via header `X-Trigger-Secret` and env `ANALYZE_TRIGGER_SECRET`). Query: `conflict`. |

---

## Agents

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/agents/status` | Per-agent status from last completed analysis (e.g. duration, sources, errors). |
| GET | `/api/agents/health` | Per-source health from HealthRegistry (availability, latency, circuit state). |
| GET | `/api/agents/history` | Last N analysis run summaries. Query: `limit` (default 20). |

---

## Proximity

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/proximity/strikes` | Proximity strike-related data. |
| GET | `/api/proximity/analyze` | Run proximity correlation/analysis. |
| GET | `/api/proximity/tunnel-sites` | Tunnel/site data for proximity. |
| POST | `/api/webhooks/proximity-events` | Webhook for proximity events. |
| GET | `/api/webhooks/proximity-events/{job_id}` | Status of a proximity-events job. |

---

## Chokepoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chokepoints/overrides` | Chokepoint overrides (e.g. custom definitions). |
| POST | `/api/chokepoints/overrides` | Set chokepoint overrides. |

---

## IAEA / NOTAM

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/iaea-tracker` | IAEA tracker result (e.g. OE-III flight, NOTAMs, press). |
| GET | `/api/notam` | NOTAMs. Query: e.g. `locations`, `limit`, `offset`. |

---

## Events

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/conflict-events` | Conflict events for the theatre. |
| GET | `/api/theater-events` | Theater map events. |

---

## Compliance

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/compliance/sanctions-check` | Sanctions search (entities/lists). |
| GET | `/api/compliance/zones` | Sanctions zones (e.g. for geofencing). |
| GET | `/api/compliance/threshold-policy` | Threshold policy for compliance. |
| POST | `/api/compliance/document-qa` | Document Q&A for compliance. |
| POST | `/api/compliance/route-screening` | Screen a route (e.g. shipping). |
| GET | `/api/compliance/intermediary-policy` | Intermediary policy. |
| POST | `/api/compliance/risk-score` | Compute compliance risk score. |

---

## Documents

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/documents/ingest` | Ingest a document (e.g. PDF URL) for later Q&A. |
| GET | `/api/documents` | List ingested documents. |
| POST | `/api/documents/qa` | Question-answering over ingested documents. |

---

## GreyNoise

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/greynoise/{conflict}` | GreyNoise snapshot for the conflict. |
| GET | `/api/greynoise/{conflict}/trend` | GreyNoise trend data. |

---

## Export

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/export/pdf` | Generate PDF export (e.g. briefing). |

---

## WebSocket

| Path | Description |
|------|-------------|
| WS | `/ws/{conflict}` | Live updates for the conflict: sends cached result on connect, then periodic pushes (e.g. every 60s). |

---

## Request/Response Notes

- **Analysis payload:** The cached and streamed analysis object contains at least `escalation_score`, `key_findings`, and per-agent keys (`finint`, `sigint`, `news`, …) with agent-specific scores and lists. See [AGENTS.md](AGENTS.md) for per-agent output fields.
- **Errors:** Endpoints return JSON with `error` or `message` on failure; streaming uses SSE `event: error` with a JSON body.
- **CORS:** Configure `CORS_ORIGINS` on the backend to include the frontend origin (e.g. `https://digital-war-room.com`).

---

## References

- [Architecture](ARCHITECTURE.md)
- [Agents](AGENTS.md)
- [API keys & env](API-KEYS.md)
- [Deployment](DEPLOYMENT.md)

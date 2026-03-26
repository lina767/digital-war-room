# Digital War Room - Complete Project Documentation

This document is the central technical documentation for the Digital War Room codebase.
It is based on the current repository structure and implementation.

---

## 1) Project Overview

Digital War Room is an AI-powered OSINT platform for conflict monitoring. It combines:

- a React + TypeScript frontend dashboard
- a FastAPI backend
- a multi-agent analysis pipeline (FININT, SIGINT, GEOINT, SOCMINT, NEWS, CYBER, ENERGY, PROTEST, DIPLO, PROXIMITY, and related modules)
- scheduled analysis jobs with in-memory state and live update channels

Main user-facing capabilities:

- near real-time conflict analysis
- cross-domain intelligence fusion
- escalation scoring and timeline
- daily briefing workflows (including newsletter sending)
- transparency via source-oriented outputs and documentation pages

### What you can do

- Monitor escalation in near real time across active conflict theaters.
- Review fused intelligence from GEOINT, SIGINT, SOCMINT, FININT, CYBER, and additional domain agents.
- Track key findings, anomalies, and risk indicators in one operational dashboard.
- Access backend APIs for analysis, monitoring, compliance workflows, document Q&A, and export use cases.
- Run recurring briefing workflows, including daily intelligence summaries and newsletter delivery.
- Audit source transparency via methodology and source-directory documentation.

### Quick links

- **Getting Started:** [README setup section](https://github.com/lina767/digital-war-room#getting-started)
- **Architecture:** [docs/ARCHITECTURE.md](https://github.com/lina767/digital-war-room/blob/main/docs/ARCHITECTURE.md)
- **Features & Interface:** [docs/how-it-works.md](https://github.com/lina767/digital-war-room/blob/main/docs/how-it-works.md) — in-app: [Documentation hub](https://digital-war-room.com/docs/documentation?doc=how-it-works)
- **Data Sources:** [docs/source-directory.md](https://github.com/lina767/digital-war-room/blob/main/docs/source-directory.md) — in-app: [Source Directory (embedded)](https://digital-war-room.com/docs/documentation?doc=source-directory)
- **Contributing:** [CONTRIBUTING.md](https://github.com/lina767/digital-war-room/blob/main/CONTRIBUTING.md)
- **API Reference:** [docs/API-REFERENCE.md](https://github.com/lina767/digital-war-room/blob/main/docs/API-REFERENCE.md)

### License

Digital War Room is released under the [MIT License](https://github.com/lina767/digital-war-room/blob/main/LICENSE).

---

## 2) Tech Stack

### Frontend

- React 18
- TypeScript
- Vite
- Tailwind CSS + shadcn-style UI components
- React Router
- Vercel Analytics

### Backend

- Python 3.11+
- FastAPI
- Pydantic v2
- httpx
- SlowAPI (rate limiting)
- structlog + Sentry + OpenTelemetry (optional observability)

### Infrastructure

- Frontend deployment target: Vercel
- Backend deployment target: Railway
- Optional local database/container stack via Docker Compose:
  - `pgvector/pgvector:pg16`
  - backend service
  - frontend service

---

## 3) Repository Structure

```text
digital-war-room/
|- backend/
|  |- agents/             # Agent logic + orchestration (CEO/supervisor, DAG, divisions)
|  |- api/                # REST/SSE route modules
|  |- services/           # shared services (state, queue, HTTP client, integrations)
|  |- middleware/         # rate limiting and API middleware
|  |- models/             # shared typed models (analysis result contracts)
|  |- tests/              # backend tests
|  |- main.py             # FastAPI app entrypoint + lifecycle jobs + WebSockets
|  |- requirements.txt
|  |- .env.example
|- src/
|  |- pages/              # route pages (Dashboard, Methodology, Support, etc.)
|  |- components/         # UI components and dashboard feature blocks
|  |- hooks/              # websocket and app hooks
|  |- lib/                # constants, helpers, content mapping
|  |- App.tsx             # frontend route registration
|- docs/                  # architecture, API, deployment, security, and domain docs
|- docker-compose.yml
|- README.md
```

---

## 4) Runtime Architecture

### Backend lifecycle (`backend/main.py`)

On startup, the backend:

1. initializes observability
2. initializes state (`StateService`) and runtime buffers
3. starts a periodic analysis task (`AUTO_ANALYZE_CONFLICT`, `AUTO_ANALYZE_INTERVAL_SEC`)
4. starts background worker queue
5. optionally starts GreyNoise schedulers when API key is configured
6. optionally starts newsletter daily loop when Resend is configured
7. warms shared HTTP client pools

On shutdown, the backend cancels tasks and closes the HTTP client cleanly.

### Analysis flow

- Public entrypoints are exposed through the supervisor/orchestration layer.
- Analysis results are cached in-memory.
- State helpers maintain:
  - latest analysis per conflict
  - last error per conflict
  - escalation timeline points
  - per-agent status snapshots
  - run history

### Frontend data flow

- Dashboard uses websocket + API-driven conflict state updates.
- UI renders:
  - threat level
  - signal counts
  - per-agent panels
  - map and feed components
  - timeline and briefing-style summaries
- Content pages (`ContentPageLayout`) use full available width by default on desktop (`w-full`, no max-width cap); responsive horizontal padding remains via Tailwind breakpoints.

---

## 5) Local Development

## 5.1 Prerequisites

- Node.js 18+ (Node 20 recommended)
- npm
- Python 3.11+
- pip

## 5.2 Frontend

```bash
npm install
npm run dev
```

Default local frontend URL:

- `http://localhost:8080` (or Vite default if port is overridden)

## 5.3 Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Default backend URL:

- `http://localhost:8000`

## 5.4 Full stack with Docker

```bash
docker compose up --build
```

Services:

- frontend: `http://localhost:8080`
- backend: `http://localhost:8000`
- postgres/pgvector: `localhost:5432`

For local development overrides:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

---

## 6) Environment Configuration

### Frontend env

Core variables:

- `VITE_API_URL` (required): backend base URL
- `VITE_APP_ENV` (optional): environment label

Example:

```env
VITE_API_URL=http://localhost:8000
VITE_APP_ENV=development
```

### Backend env

Use `backend/.env.example` as the canonical template.

Critical variables:

- LLM provider keying (at least one strategy):
  - `ANTHROPIC_API_KEY`
  - or `LLM_PROVIDER=openai` + `OPENAI_API_KEY`
- data-provider keys (depending on enabled features), e.g.:
  - `NEWS_API_KEY`
  - `NASA_FIRMS_KEY`
  - `ALPHAVANTAGE_API_KEY`

Common optional groups:

- analysis cost and model tuning
- additional source integrations (OTX, GreyNoise, ACLED, Shodan, Firecrawl, etc.)
- observability (`SENTRY_*`, `OTEL_*`)
- newsletter (`RESEND_API_KEY`, `NEWSLETTER_FROM`, `FRONTEND_URL`, etc.)
- CORS (`CORS_ORIGINS` for production hardening)

---

## 7) API Reference (Implemented Endpoints)

All routes below are mounted under `/api` unless explicitly noted.

## 7.1 Health and root

- `GET /health`
- `GET /health/ready`
- `GET /`

## 7.2 Analysis and orchestration

- `GET /api/analyze/stream` (SSE)
- `GET /api/analyze/latest`
- `GET /api/analyze/status`
- `GET /api/analyze/timeline`
- `POST /api/analyze` (returns cached analysis)
- `GET /api/analyze/refresh` (async or `sync=true`)
- `POST /api/analyze/trigger` (optional secret header)

## 7.3 Agent monitoring

- `GET /api/agents/status`
- `GET /api/agents/health`
- `GET /api/agents/history`

## 7.4 Proximity and chokepoints

- `GET /api/proximity/strikes`
- `GET /api/proximity/analyze`
- `GET /api/proximity/tunnel-sites`
- `GET /api/chokepoints/overrides`
- `POST /api/chokepoints/overrides`
- `POST /api/webhooks/proximity-events`
- `GET /api/webhooks/proximity-events/{job_id}`

## 7.5 Compliance

- `POST /api/compliance/sanctions-check`
- `GET /api/compliance/zones`
- `GET /api/compliance/threshold-policy`
- `POST /api/compliance/document-qa`
- `POST /api/compliance/route-screening`
- `GET /api/compliance/intermediary-policy`
- `POST /api/compliance/risk-score`

## 7.6 Documents

- `POST /api/documents/ingest`
- `GET /api/documents`
- `POST /api/documents/qa`

## 7.7 IAEA / NOTAM / events

- `GET /api/iaea-tracker`
- `GET /api/notam`
- `GET /api/conflict-events`
- `GET /api/theater-events`

## 7.8 GreyNoise and export

- `GET /api/greynoise/{conflict}`
- `GET /api/greynoise/{conflict}/trend`
- `POST /api/export/pdf`

## 7.9 Newsletter

- `POST /api/newsletter/subscribe`
- `GET /api/newsletter/confirm`
- `GET /api/newsletter/unsubscribe`
- `POST /api/newsletter/send-daily`

---

## 8) Real-time Channels

WebSocket endpoints:

- `WS /ws/{conflict}`: sends cached result on connect and periodic updates
- `WS /ws/social/{conflict}`: periodic social stream collection payload

Server-Sent Events endpoint:

- `GET /api/analyze/stream?conflict=...`: emits agent completion events and final supervisor event

---

## 9) Agent System Overview

The platform uses domain-specific agents with standardized output dictionaries.
Typical output includes:

- score field (domain-dependent)
- summary text
- domain lists (e.g. `aircraft`, `articles`, `hotspots`, `threat_reports`)

Core families in current project docs and code:

- FININT, SIGINT, NEWS, DIPLO, TECHINT, CYBER
- GEOINT, SOCMINT, ENERGY, PROTEST, PROXIMITY
- additional specialized layers/modules: chokepoint, narrative, compliance enrichments

The orchestration pipeline executes in waves and synthesizes into one final analysis result consumed by the UI and API clients.

---

## 10) Frontend Routing Overview

Primary routes registered in `src/App.tsx` include:

- `/demo`
- `/app/login`
- `/app/dashboard`
- `/app/monitoring`
- `/how-it-works`, `/methodology`, `/sources` → redirect to `/docs/documentation` with `?doc=how-it-works` | `methodology` | `source-directory`
- `/daily-briefing`
- `/docs/documentation`
- `/docs` → redirect to `/docs/documentation`
- `/newsletter` + confirm/unsubscribe routes
- `/support`, `/privacy`, `/impressum`
- `/blog` and `/blog/:slug`
- fallback `*` route → `NotFound`

This is a client-side routed SPA via `BrowserRouter`.

---

## 11) Quality, Tests, and Tooling

### Data quality (reliability)

- Agent contracts include roll-up fields on `BaseAgentResult` (`dq_confidence`, `data_freshness`, `source_count`, `fallback_used`, `error_summary`, `provenance_refs`); see `backend/agents/dq_contract.py`.
- After collection, CEO calls `apply_quality_to_all_agents()` and runs `run_cross_agent_quality_gate()`; results appear as `data_quality_gate` and `quality_warnings` on the analysis payload, and in the supervisor LLM user JSON as `data_quality_gate`.
- Calibration summaries: `dq_calibration_metrics` (see `backend/calibration/dq_calibration.py`).
- Env: `DQ_QUALITY_GATE_ENABLED` (default on), `DQ_SCORE_SPREAD_WARN_THRESHOLD` (default 55).
- Monitoring: `GET /api/agents/monitoring` includes `data_quality` aggregates (runs, warnings, last run).

Frontend scripts (`package.json`):

- `npm run dev`
- `npm run build`
- `npm run lint`
- `npm run typecheck`
- `npm run test`

Backend quality tools (via `backend/pyproject.toml` and requirements):

- pytest (+ coverage)
- mypy
- ruff

Typical backend validation:

```bash
cd backend
pytest
mypy .
ruff check .
```

---

## 12) Deployment

Recommended production setup:

- frontend on Vercel
- backend on Railway

Key deployment requirements:

- set backend env vars in Railway
- set frontend `VITE_API_URL` in Vercel to backend public URL
- configure `CORS_ORIGINS` for production domains
- validate health endpoints after deployment (`/health`, `/health/ready`)

Detailed rollout and production checklist:

- see `docs/DEPLOYMENT.md`

---

## 13) Security and Operational Notes

- Never commit secrets (`.env`, `backend/.env`).
- Use explicit CORS origin lists in production.
- Rate limits are enabled on conflict-bearing endpoints.
- Validate and sanitize conflict inputs before execution.
- Use trigger secret for protected analysis triggering (`ANALYZE_TRIGGER_SECRET`) when exposed publicly.
- Multi-tenancy: apply DB migrations `003`/`004`, set `SUPABASE_JWT_SECRET` or `JWT_SECRET` for HS256 user tokens, optional `MULTI_TENANCY_REQUIRE_AUTH=true` to reject unauthenticated calls. Tenant API keys: `POST /api/tenant/api-keys`. Frontend: `/app/login` and `getAuthHeaders()` in `src/lib/api.ts`.

Related docs:

- `docs/SECURITY.md`
- `docs/API-KEYS.md`
- `docs/OBSERVABILITY.md`

## 13.1 Privacy and compliance

Core governance documents:

- `docs/PRIVACY-GDPR-DSGVO.md`
- `docs/ROPA-RECORD-OF-PROCESSING.md`
- `docs/DATA-RETENTION-POLICY.md`
- `docs/AUDIT-TRAIL-POLICY.md`
- `docs/DSR-RUNBOOK.md`
- `docs/ANALYTICS-CONSENT.md`

---

## 14) Troubleshooting

### Frontend cannot reach backend

- verify `VITE_API_URL`
- check browser network/CORS
- confirm backend is running and reachable

### No analysis available

- check `/api/analyze/status?conflict=...`
- trigger a run using `/api/analyze/refresh` or `/api/analyze/trigger`
- inspect backend logs for missing API keys or source failures

### WebSocket not updating

- verify backend websocket path and proxy behavior
- check if cache exists for the conflict
- test with `/api/analyze/latest` to confirm state availability

### Newsletter does not send

- verify `RESEND_API_KEY` and `NEWSLETTER_FROM`
- check `NEWSLETTER_SEND_TIMEZONE` / `NEWSLETTER_SEND_HOUR` (or legacy `NEWSLETTER_SEND_UTC_HOUR`)
- inspect backend logs around daily scheduler window

---

## 15) Related Project Documentation

For deeper domain-specific details, use:

- `README.md` (high-level product and setup)
- `docs/ARCHITECTURE.md`
- `docs/API-REFERENCE.md`
- `docs/AGENTS.md`
- `docs/AGENT-TOOL-CHAIN.md`
- `docs/DEPLOYMENT.md`
- `docs/NEWSLETTER-SPEC.md`
- `docs/PROXIMITY-ANALYZER.md`
- `docs/SOURCE-DIRECTORY.md` (or `docs/source-directory.md`)

---

## 16) Maintenance Guidance

When updating this document, keep it aligned with:

- `src/App.tsx` route table
- `backend/main.py` lifecycle and scheduler behavior
- `backend/api/routes*.py` endpoint inventory
- `backend/.env.example` variable contract
- `package.json` and backend tool configs

This file should remain the single "start here" technical reference for onboarding and operations.

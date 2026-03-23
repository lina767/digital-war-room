<div align="center">

# Digital War Room

**AI-powered multi-agent OSINT intelligence platform**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Node 18+](https://img.shields.io/badge/node-18+-339933?logo=nodedotjs&logoColor=white)](https://nodejs.org/)

Real-time conflict monitoring with specialized agents across GEOINT, SIGINT, SOCMINT, FININT, CYBER, and related domains — orchestrated by a single Claude Sonnet supervisor with rule-based routing.

*Built at the intersection of AI engineering, international relations, and OSINT tradecraft.*

[Live site](https://digital-war-room.com) · [Issues](https://github.com/lina767/digital-war-room/issues)

</div>

---

## What is Digital War Room?

Digital War Room deploys **11 specialized OSINT agents** — supervised by a Claude Sonnet orchestrator — to monitor, analyze, and synthesize intelligence from open sources. The stack applies structured analytical frameworks so raw signals become assessments with source attribution, not just aggregated headlines.

**Why it matters:** Many dashboards show *what happened*. Digital War Room aims to help you interpret *what it may mean* — by cross-referencing domains such as sanctions data, flight patterns, protest activity, and commodity flows.

---

## Documentation

| Topic | Repository |
|--------|----------------|
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| How it works (UX & flows) | [docs/how-it-works.md](docs/how-it-works.md) |
| API overview | [docs/API-REFERENCE.md](docs/API-REFERENCE.md) |
| Deployment & env | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| API keys & backend config | [docs/API-KEYS.md](docs/API-KEYS.md) |
| Full project index | [docs/PROJECT-DOCUMENTATION.md](docs/PROJECT-DOCUMENTATION.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLAUDE SONNET SUPERVISOR                       │
│         Orchestrates agents · Resolves conflicts · Briefs        │
└──────────────┬──────────────────────────────────┬───────────────┘
               │                                  │
    ┌──────────▼──────────┐            ┌──────────▼──────────┐
    │   INTELLIGENCE LAYER │            │   MONITORING LAYER   │
    │                      │            │                      │
    │  📡 SIGINT Agent     │            │  🌍 GEOINT Agent     │
    │  💰 FININT Agent     │            │  📱 SOCMINT Agent    │
    │  🔒 CYBER Agent      │            │  📰 NEWS Agent       │
    │  🏛️ DIPLO Agent      │            │  ⚡ ENERGY Agent     │
    │  🔬 TECHINT Agent    │            │  ✊ PROTEST Agent    │
    │                      │            │  📍 PROXIMITY Agent  │
    └──────────┬───────────┘            └──────────┬───────────┘
               │                                   │
    ┌──────────▼───────────────────────────────────▼──────────┐
    │                      DATA SOURCES                        │
    │  ACLED · GDELT · OONI · IODA · Polymarket · ADS-B       │
    │  GreyNoise · OpenSanctions · OFAC · EU Sanctions List    │
    └─────────────────────────────────────────────────────────┘
```

---

## Agent overview

| Agent | Role | Key data sources | Often pairs with |
|-------|------|------------------|------------------|
| **SIGINT** | Flight patterns, airspace, ADS-B | ADS-B Exchange, Flightradar24 | GEOINT, PROXIMITY |
| **FININT** | Sanctions, ownership chains, commodities | OpenSanctions, OFAC SDN, EU list | ENERGY, DIPLO |
| **GEOINT** | Geographic conflict events, mapping | ACLED, GDELT | SIGINT, NEWS |
| **SOCMINT** | Social narratives, sentiment | X/Twitter, Telegram | PROTEST, NEWS |
| **NEWS** | Breaking news, multilingual | RSS, wires | All agents |
| **CYBER** | Outages, DDoS, hacktivism | GreyNoise, OONI, IODA | SIGINT, TECHINT |
| **ENERGY** | Infrastructure, Hormuz / commodity stress | Maritime AIS, oil APIs | FININT, GEOINT |
| **TECHINT** | Tech / defense industry signals | SIPRI, defense wires | SIGINT, DIPLO |
| **PROTEST** | Unrest, crackdowns | ACLED, SOCMINT | SOCMINT, CYBER |
| **DIPLO** | Diplomatic / legal signals | UN, ICJ, sanctions lists | FININT, ENERGY |
| **PROXIMITY** | Geographic risk / proximity | FIRMS, OSM | GEOINT, SIGINT |

---

## Key features

- **Interactive theater map** — Conflict visualization with overlays (events, flights, maritime, protests).
- **Daily intelligence briefings** — Synthesized assessments with confidence and attribution.
- **Predictive outlook** — Scenario-style views using market-implied signals (e.g. Polymarket) where configured.
- **Source directory** — Trace claims back to primary sources with reliability context.
- **Strait of Hormuz monitor** — Maritime and commodity stress through the chokepoint.
- **Sanctions-oriented workflows** — OFAC / EU / UN screening patterns where APIs and keys are configured.

---

## Tech stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, shadcn-style UI |
| **Backend** | Python 3.11+, FastAPI, Pydantic |
| **AI** | Claude Sonnet (supervisor), rule-based agent dispatch |
| **Hosting** | Vercel (frontend), Railway (backend) |
| **Analytics** | Vercel Analytics |

---

## Why rule-based routing + Claude supervisor (not LangGraph)?

The project moved from a full LangGraph multi-agent graph to a **hybrid**: rule-based dispatch with one Claude Sonnet supervisor for synthesis. That reduced token cost substantially while keeping analytical quality for contradiction resolution, source weighting, and natural-language briefings.

---

## Getting started

### Prerequisites

- Node.js 18+
- Python 3.11+

### Frontend

```bash
git clone https://github.com/lina767/digital-war-room.git
cd digital-war-room
npm install
npm run dev
# → http://localhost:8080
```

### Backend

```bash
cd backend
pip install -r requirements.txt
# optional: lint, tests, types
pip install -r requirements-dev.txt
uvicorn main:app --reload
# → http://localhost:8000
```

### Environment variables

In the **project root**, create `.env` as needed:

```env
VITE_API_URL=http://localhost:8000
```

Copy and fill examples from:

- Root: `.env.development.example`, `.env.staging.example`, `.env.production.example`
- Backend: `backend/.env.example` and `backend/.env.*.example`

Secrets are documented in [docs/API-KEYS.md](docs/API-KEYS.md).

### Docker Compose (full stack)

```bash
docker compose up --build
```

- Frontend: `http://localhost:8080`
- Backend: `http://localhost:8000`
- Postgres (pgvector): `localhost:5432`

---

## API quick reference

Base URL (local): `http://localhost:8000`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness |
| `/api/analyze/status?conflict=Iran` | GET | Cache / error status |
| `/api/analyze/latest?conflict=Iran` | GET | Latest cached analysis |
| `/api/analyze/refresh?conflict=Iran` | GET | Trigger background refresh |
| `/api/analyze/stream?conflict=Iran` | GET (SSE) | Stream agent + supervisor events |
| `/api/agents/status` | GET | Last per-agent snapshot |
| `/api/agents/history` | GET | Recent run history |

Interactive docs: `http://localhost:8000/docs` (local). See [docs/API-REFERENCE.md](docs/API-REFERENCE.md) for more.

### Backend request flow

```mermaid
flowchart LR
    A[Client] --> B[/FastAPI Routes/]
    B --> C[Supervisor]
    C --> D[Specialized Agents]
    D --> E[(StateService Cache)]
    E --> B
```

---

## Code quality & tests

Backend tests live under `backend/tests/` (`test_agents/`, `test_integration/`, `test_api/`, `conftest.py`).

```bash
cd backend
pytest
mypy .
ruff check .
```

Coverage uses `pytest-cov` with a minimum threshold (see `pytest` config in the backend).

[`.pre-commit-config.yaml`](.pre-commit-config.yaml) can run Ruff, mypy, and Prettier — install with `pre-commit install` if you use it locally.

---

## Scripts (frontend)

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server (Vite) |
| `npm run build` | Production build |
| `npm run preview` | Preview production build |
| `npm run lint` | ESLint |
| `npm run test` | Vitest |
| `npm run typecheck` | TypeScript check |
| `npm run version:patch` / `minor` / `major` | SemVer bump |

---

## DevOps & maintenance

- **Dependabot:** [`.github/dependabot.yml`](.github/dependabot.yml) — automated updates for GitHub Actions, npm, and pip.
- **Versioning:** [CHANGELOG.md](CHANGELOG.md) follows the project’s release notes.

---

## Roadmap

- [ ] Multi-theater support (beyond Middle East)
- [ ] Collaborative annotation layer
- [ ] API access for researchers
- [ ] Webhook-based alerts
- [ ] Mobile-optimized briefing view
- [ ] Integration with Bellingcat-style verification tooling

---

## Contributing

Contributions are welcome — new data pipelines, agent improvements, or UI fixes.

1. Fork the repository  
2. Branch (`git checkout -b feature/your-feature`)  
3. Commit with clear messages  
4. Push and open a Pull Request  

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup and how to report issues.

---

## License

[MIT License](LICENSE) — Copyright (c) 2026 Lina Braun.

---

<div align="center">

**Lina Braun** — Political science & AI engineering

[Live site](https://digital-war-room.com) · [Report a bug](https://github.com/lina767/digital-war-room/issues) · [Feature request](https://github.com/lina767/digital-war-room/issues)

</div>

# Architecture & Layers

This document defines the backend layers and dependency rules. See [ARCHITECTURE-ROADMAP.md](ARCHITECTURE-ROADMAP.md) for the improvement plan.

---

## Layer overview

| Layer | Responsibility | Allowed to use |
|-------|----------------|----------------|
| **API** | HTTP, WebSocket, request/response, auth | Orchestration, state service, models |
| **Orchestration** | DAG, CEO, run lifecycle, streaming | Agents (registry), state service, models |
| **Agents** | Domain logic, tools, external APIs | Config, shared context types, HTTP client |
| **Services** | Cross-cutting: state (in-memory), job queue, HTTP client | Config; must not import agents |
| **Data / external** | ACLED, OFAC, GreyNoise, etc. | Used by agents and services |

---

## Dependency rules

- **Orchestration** does not import from `api/`.
- **Agents** do not import from `ceo` or `supervisor` (they are invoked via registry).
- **Services** do not import from `agents/` (state_service, job_queue, http_client are used by API and orchestration).
- Shared types (e.g. `AnalysisResult`, `AgentContext`) live in `models/` or `agents/contracts.py` and are used by both orchestration and API.

---

## Execution path

1. **Entry:** `analyze_conflict(conflict)` and `run_analysis_streaming(conflict)` in `agents/supervisor.py` are the public entrypoints.
2. **Pipeline:** Both delegate to `agents/ceo.analyze_conflict_dag` / `analyze_conflict_dag_streaming`. DAG order: WAVE1 agents (finint, sigint, news, diplo, techint, cyber) → `agent_context` (shared context) → WAVE2 agents (geoint, socmint, energy, civil unrest, proximity, chokepoint, narrative) → division summaries → CEO synthesis.
3. **Division summaries:** Pure functions (scores + anomalies + rule-based text). No LLM by default; set `USE_DIVISION_HAIKU=1` to enable optional Haiku per division.
4. **State:** Cache, agent status, escalation timeline, and run history are stored via `StateService` (in-memory).
5. **API:** Routes in `api/routes.py` read/write state through the state service and return typed `AnalysisResult` where applicable.

---

## Key modules

| Module | Layer | Role |
|--------|-------|------|
| `api/routes.py` | API | REST and SSE for analyze, status, history, timeline |
| `agents/supervisor.py` | Orchestration | Public API; delegates to CEO |
| `agents/ceo.py` | Orchestration | DAG build, CEO synthesis, response shape |
| `agents/dag_scheduler.py` | Orchestration | Topological execution of nodes |
| `agents/division.py`, `agents/divisions/*.py` | Orchestration | Division aggregation and summaries |
| `agents/registry.py` | Orchestration | Agent discovery and entry functions |
| `agents/context.py` | Shared | `AgentContext`, `build_context_from_results` (WAVE1/WAVE2) |
| `services/state_service.py` | Services | Cache and state (in-memory) |
| `services/source_fetch.py` | Services | Per-run cache to deduplicate external API calls |
| `models/analysis.py` | Shared | `AnalysisResult` for API/orchestration boundary |

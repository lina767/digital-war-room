# Architecture Roadmap

Direction for tightening the backend and agent layer: single execution model, proper persistence, clearer layers, strict typing, and better agent collaboration.

---

## 1. Single mode: DAG only (kill legacy supervisor)

**Current:** `supervisor.py` branches on `USE_DAG_ANALYSIS` (default `1`). When true it delegates to `ceo.analyze_conflict_dag` / `analyze_conflict_dag_streaming`; when false it uses `_collect_all_agents` (single-phase or handoff). All entry points still go through `analyze_conflict()` / `run_analysis_streaming()`.

**Target:** One execution path. DAG + CEO are the only implementation. No env toggle, no `_collect_all_agents*` or legacy handoff in the hot path.

**Concrete:**

- [x] Make `analyze_conflict(conflict)` and `run_analysis_streaming(conflict)` in `supervisor.py` **only** call `ceo.analyze_conflict_dag` / `analyze_conflict_dag_streaming`. Remove `_use_dag_analysis()`, `_collect_all_agents`, `_collect_all_agents_single_phase`, `_collect_all_agents_handoff`. **(Done.)**
- [ ] Move any logic that only the legacy path used (e.g. `_previous_sigint` for AIS gap detection) into DAG nodes or a small shared module used by the DAG.
- [ ] Delete or archive legacy collection code; keep `context.py` and handoff-style context **only** if reused inside the DAG (e.g. context built from earlier nodes and passed to later ones).
- [ ] Update tests: `test_integration.py` and any tests that assert on the legacy path; point them at the DAG API.
- [ ] Remove `USE_DAG_ANALYSIS` from env/docs; document that analysis is always DAG-driven.

**Outcome:** Single code path, easier reasoning and refactors.

---

## 2. Persistence: Redis + Postgres (no in-memory state)

**Current:** `main.py` lifespan sets `app.state.analysis_cache`, `analysis_last_error`, `escalation_timeline_history`, `agent_status_last`, `analysis_run_history`, `job_queue`, `ws_manager`. All process-local; restarts lose state; no sharing across instances.

**Target:**

- **Redis:** Cache and volatile state. Analysis result cache (e.g. `conflict -> {result, at}`), agent status, escalation timeline tail, job queue (if not using a dedicated queue backend), rate-limit / cooldown state. TTLs where appropriate.
- **Postgres:** Durable history. Run history (who, when, conflict, outcome, duration), escalation timeline (long-term), audit trail for compliance. Optional: store last N analysis payloads for replay/debug.

**Concrete:**

- [ ] Introduce a **state service** (e.g. `services/state_service.py` or `services/cache.py`): interface for “get/set analysis cache”, “append escalation point”, “get run history”, “record agent status”. Implementation: Redis for cache/state, Postgres for history.
- [ ] **Redis:** Connection pool (e.g. `redis.asyncio` or `aioredis`). Keys: e.g. `dwr:cache:{conflict}`, `dwr:timeline:{conflict}`, `dwr:agent_status:{agent_key}`, `dwr:run_history` (or use a list). Set TTLs on cache keys (e.g. 1h or configurable).
- [ ] **Postgres:** Tables (or migrations): e.g. `analysis_runs` (id, conflict, started_at, finished_at, status, duration_ms, payload_ref), `escalation_timeline` (conflict, at, score, optional metadata). Use existing pgvector setup if present; keep history in normal tables.
- [x] **Lifespan:** In `main.py`, init StateService and set `app.state.state_service`. Legacy in-memory dicts kept for fallback. **(Done; Redis optional via REDIS_URL.)**
- [x] **Routes:** `api/routes.py` — use state service when present for cache, last_error, timeline, agent_status, run_history. Preserve existing API shape. **(Done.)**
- [ ] Env: `REDIS_URL`, `DATABASE_URL` (or existing Postgres env); document in `API-KEYS.md` or `DEPLOYMENT.md`. Fallback: if Redis is down, either fail fast or degrade (e.g. no cache, in-memory fallback for a single instance) and document.

**Outcome:** Restart-safe, multi-instance-safe, and a clear place to add retention/audit policies.

---

## 3. Division layer: simplify or flatten

**Current:** Division heads (`division.py`, `divisions/*.py`) own weighted score, anomaly detection, optional Haiku summary. DAG has per-division summary nodes (Tier 4) and then CEO synthesis. Adds one more layer between raw agents and the final brief.

**Target:** Either **simplify** (keep divisions but make them thin: aggregate scores + pass-through, no extra LLM unless clearly justified) or **flatten** (agents → CEO only; aggregate scores in the DAG or in the CEO step). Decision depends on how much value division-level summaries and anomalies provide to the product.

**Concrete (simplify):**

- [ ] Document the exact value of each division: e.g. “Military division summary is used in the UI here; anomaly is used there.” If the only consumer is the CEO, consider moving aggregation into the CEO and dropping division summary nodes.
- [ ] If keeping divisions: make them **pure functions** of agent results (no I/O, no LLM) for the default path; optional “division briefing” as a separate, explicitly configured node (e.g. only for “daily briefing” view).
- [ ] If flattening: remove division summary nodes from the DAG; CEO takes raw agent results + optional shared context; scoring/weighting lives in the CEO or in a single “aggregation” node. Division becomes a **grouping in the registry only** (for config and UI), not an execution layer.

**Outcome:** Less moving parts and clearer responsibility: either “divisions = lightweight aggregation” or “no division execution, only CEO + agents.”

---

## 4. Strict typing: Pydantic end-to-end

**Current:** Many functions take or return `Dict[str, Any]`; agent contracts and API responses are only partially modeled.

**Target:** Public boundaries use Pydantic models: agent **input** (e.g. `AgentInput(conflict, context?)`), agent **output** (per-agent result model, e.g. `SigintResult`, `NewsResult`), **analysis result** (full response from `analyze_conflict`), **API request/response** bodies. Internal code can still use dicts where it’s pragmatic, but all cross-module and API boundaries are typed.

**Concrete:**

- [ ] **Contracts:** In `agents/contracts.py` (or a dedicated `models/` package), define response models per agent (or one `AgentResult` with a discriminated union by agent name). Replace fallback dicts with these models; agents return typed instances (or serialize to dict for storage).
- [ ] **Supervisor/CEO:** `analyze_conflict` return type: e.g. `AnalysisResult` (Pydantic) with `escalation_score`, `threat_level`, `key_findings`, `summary`, per-agent results as typed sub-models. Streaming can yield a union type (e.g. `StreamEvent` with `node_id`, `payload`).
- [ ] **API:** Request/response models for `/api/analyze`, `/api/agents/status`, `/api/agents/history`, etc. Use Pydantic in FastAPI route signatures and response_model.
- [ ] **State service:** Cache/history payloads: store as JSON; when reading, parse into Pydantic models so that routes return typed data.
- [ ] Incremental: start with the **final analysis result** and **one agent** (e.g. SIGINT), then roll out to the rest and to the API.

**Outcome:** Safer refactors, better docs, and validation at the edges.

---

## 5. Clear architectural layers

**Current:** Organic growth: agents, divisions, supervisor, CEO, compliance, services, API routes all reference each other in various ways; no explicit layering.

**Target:** Define a small number of layers and dependencies (e.g. “API → orchestration → agents & services → data sources”). Document and enforce (e.g. “orchestration does not import from API”).

**Proposed layers:**

| Layer | Responsibility | Allowed to use |
|-------|----------------|----------------|
| **API** | HTTP, WebSocket, request/response, auth | Orchestration, state service |
| **Orchestration** | DAG, CEO, run lifecycle, streaming | Agents (registry), state service, models |
| **Agents** | Domain logic, tools, external APIs | Config, shared context types, http client |
| **Services** | Cross-cutting: state (Redis/Postgres), job queue, HTTP client, ACLED refresh | Config, no agents |
| **Data / external** | ACLED, OFAC, GreyNoise, etc. | Used by agents and services |

**Concrete:**

- [ ] Add a short **architecture** section to the docs (e.g. in this file or `ARCHITECTURE.md`) with a diagram and the table above. State that “orchestration does not import from `api/`”, “agents do not import from `ceo` or `supervisor`”, etc.
- [ ] Optional: a small lint or test that checks import rules (e.g. `api/` not importing from `agents` except for a narrow bridge). Start with documentation only if preferred.
- [ ] Move shared types (e.g. `AgentContext`, analysis result model) into a `models/` or `contracts/` package used by orchestration and agents so that dependency direction is clear.

**Outcome:** Clear dependency direction and a single place to look for “where does X belong?”

---

## 6. Agent efficiency and collaboration

**Current:** Handoff exists in the legacy path (wave 1 → context → wave 2). DAG runs nodes in dependency order; context can be passed via DAG node outputs. Some agents may call the same external APIs (e.g. same conflict, same source) without sharing.

**Target:** (a) Shared context: all context-aware agents get a single, structured context (regions, entities, peer summaries, key findings). (b) Deduplicate external calls: shared “source fetch” or cache for expensive calls (e.g. ACLED, OFAC list) keyed by conflict + scope. (c) Clear contracts so agents can consume each other’s outputs without re-fetching.

**Concrete:**

- [ ] **Context in the DAG:** Define a “context builder” node (or a few) that run after foundation agents and produce a structured context (Pydantic model). Downstream nodes (GEOINT, SOCMINT, etc.) take this context as input; agents accept `(conflict, context)` and use it to focus queries (e.g. `focus_regions`, `focus_entities`). Reuse or adapt `AgentContext` and `build_context_from_results` in the DAG.
- [x] **Shared fetch/cache:** Added `services/source_fetch.py` (per-run cache, cleared at DAG start). **(Done.)** Original: Identify APIs that multiple agents call (e.g. ACLED, sanctions lists, same RSS). Introduce a **source layer** (e.g. `services/source_fetch.py` or per-source modules) that agents call instead of hitting the API directly. Cache by (conflict, source, params) with short TTL; one fetch per run per key. Document “agents should use shared fetch for X, Y, Z”.
- [ ] **Contracts:** Ensure agent output models expose the fields that other agents or the CEO need (e.g. `aircraft`, `ships`, `summary`) so that context builder and CEO can rely on typed data instead of ad-hoc dict keys.
- [ ] **Efficiency review:** Audit one run: which external HTTP calls are made multiple times for the same logical input? Add shared fetch or pass-through from an earlier node (e.g. “ACLED events” node → consumed by GEOINT and CIVIL_UNREST).

**Outcome:** Fewer redundant calls, consistent context for downstream agents, and a path to better briefs without more API cost.

---

## Suggested order of work

1. **1 + 5** — Commit to DAG-only and document layers. Low risk, removes branching and clarifies structure.
2. **4** — Introduce Pydantic for the analysis result and one agent; then roll out. Makes later changes safer.
3. **2** — Add Redis + Postgres and the state service; migrate one piece of state (e.g. analysis cache), then the rest. Enables multi-instance and durability.
4. **3** — Simplify or flatten divisions based on product need; adjust DAG and registry accordingly.
5. **6** — Context in DAG, shared fetch/cache, and deduplication. Iterate with one shared source and one consumer.

---

## References

- Current entry: `agents/supervisor.py` (`analyze_conflict`, `run_analysis_streaming`)
- DAG + CEO: `agents/ceo.py`, `agents/dag_scheduler.py`
- State: `main.py` lifespan, `api/routes.py` (cache, timeline, status, history)
- Divisions: `agents/division.py`, `agents/divisions/*.py`
- Context: `agents/context.py`
- Contracts: `agents/contracts.py`

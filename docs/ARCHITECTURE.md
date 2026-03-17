# Architecture

High-level overview of the Digital War Room pipeline: agent pool, supervisor, caching, and periodic analysis.

---

## Pipeline Overview

1. **Conflict** — A string (e.g. `"Iran"`) identifies the theatre. All agents receive the same conflict and return a structured payload.
2. **Agent pool** — 12 runnables in parallel: FININT, SIGINT, NEWS, GEOINT, SOCMINT, TECHINT, CYBER, ENERGY, PROTEST, DIPLO, PROXIMITY, narrative (signal framework), and chokepoint. Plus ACLED reference fetches. Each has a 75s timeout; failures yield fallback dicts.
3. **Supervisor** — Fuses all agent outputs (scores, summaries, lists) into one assessment via an LLM (Claude or GPT-4o). Produces escalation score, key findings, scenarios, and compliance-related fields.
4. **Post-processing** — Narrative/signal framework, compliance layer (geofencing, AIS anomaly, supply-chain, OFAC/EU), predictive block (24h outlook). Optional NER enrichment and actor list for the conflict.
5. **Cache** — Latest analysis per conflict is stored in memory (and optionally persisted). Dashboard and API serve from cache; background job refreshes on an interval (e.g. every 6h or 24h).
6. **Frontend** — React dashboard: threat level, key findings, agent cards, map overlays (Theater Map, Daily Briefing, Predictive Outlook). Can consume streaming (`/api/analyze/stream`) or cached (`/api/analyze/latest`).

---

## Key Components

| Component | Role |
|-----------|------|
| **ThreadPoolExecutor** | Runs all agents in parallel (max 14 workers). No heavy agent framework; each agent is a function `run_*_agent(conflict: str) -> Dict`. |
| **Supervisor LLM** | Single LLM call (or rule-based fallback) to synthesize scores and raw outputs into one BLUF-style assessment. |
| **Analysis cache** | In-memory `analysis_cache[conflict]`; optional persistence. Frontend and `/api/analyze/latest` read from it. |
| **Periodic analysis** | Background task (configurable interval, e.g. `AUTO_ANALYZE_INTERVAL_SEC`) runs full pipeline for `AUTO_ANALYZE_CONFLICT`, updates cache and timeline. |
| **WebSocket** | Optional live updates: escalation timeline, agent status, run history pushed to connected clients. |

---

## Design Decisions

- **No heavy agent frameworks** — Pure Python, `ThreadPoolExecutor`, direct LLM SDK (Anthropic/OpenAI). Each agent returns a Dict with at least a score field and domain-specific lists.
- **Graceful degradation** — Missing API keys → empty results, no crash. LLM failure → rule-based scoring. Per-agent timeout keeps one slow source from blocking the run.
- **Dual-mode agents** — Env `USE_RULE_BASED_AGENTS`: when true, agents use fixed tool chains (no LLM in agents); when false, Haiku can drive tool selection. Supervisor can also be rule-only (`USE_RULE_BASED_SUPERVISOR`).
- **Compliance built-in** — Geofencing, AIS anomaly detection, supply-chain screening, OFAC/EU cross-checks run after collection; results are part of the unified payload.

---

## Data Flow

```
Conflict (e.g. "Iran")
    → ThreadPoolExecutor: run_finint_agent, run_sigint_agent, ... run_chokepoint_agent
    → Per-agent Dict (scores, lists, summaries)
    → Supervisor: LLM or rule-based fusion
    → Post-process: narrative, compliance, predictive, actors
    → Cache + optional WebSocket push
    → Frontend / API consumers
```

---

## Observability

- **OpenTelemetry** — When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, traces (analysis.collection, supervisor, etc.) are sent to an OTLP endpoint (e.g. Jaeger).
- **Logging** — Standard Python logging; agent timeouts and errors are logged with agent name and conflict.

---

## References

- [One-pager (diagram & agent table)](social-assets/one-pager.md)
- [Agents (per-agent description)](AGENTS.md)
- [API reference](API-REFERENCE.md)
- [Deployment](DEPLOYMENT.md)

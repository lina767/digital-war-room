import { apiFetch, apiUrl, DEFAULT_FETCH_TIMEOUT_MS, getApiBase } from "./client";

/** Per-source fetch result (backend agents telemetry). */
export interface SourceResult {
  name: string;
  status: "ok" | "degraded" | "error";
  fetched_at?: string;
  duration_ms?: number;
  record_count?: number;
  error?: string;
  cached?: boolean;
  reference_urls?: string[];
  endpoint_kind?: string;
}

/** One append-only processing step in an agent pipeline. */
export interface ProcessingStep {
  step: string;
  at?: string;
  detail?: string;
}

/** Confidence metadata for an agent score. */
export interface ScoreConfidence {
  level: string;
  sources_ok: string[];
  sources_missing: string[];
}

/** Agent telemetry attached to each agent result (_meta). */
export interface AgentMeta {
  agent: string;
  fetched_at: string;
  duration_ms: number;
  sources: SourceResult[];
  confidence: ScoreConfidence;
  data_freshness: "live" | "recent" | "stale" | "unavailable";
  data_confidence?: "live" | "estimated" | "degraded";
  fallback_used?: boolean;
  error_summary?: string | null;
  processing_steps?: ProcessingStep[];
  analysis_run_id?: string | null;
}

/** GET /api/agents/health – per-source health from HealthRegistry. */
export interface AgentsHealthSource {
  source: string;
  agent: string;
  availability_pct: number;
  avg_latency_ms: number | null;
  status: "ok" | "degraded" | "down";
  circuit_open: boolean;
  last_error: string | null;
  last_results_count: number;
}
export interface AgentsHealthResponse {
  sources: AgentsHealthSource[];
  summary: { total_sources: number; degraded: number; down: number; ok: number };
}
export async function getAgentsHealth(): Promise<AgentsHealthResponse | null> {
  try {
    const res = await apiFetch(apiUrl("agents/health"), { method: "GET", timeoutMs: DEFAULT_FETCH_TIMEOUT_MS });
    if (!res.ok) return null;
    return (await res.json()) as AgentsHealthResponse;
  } catch {
    return null;
  }
}

/** GET /api/agents/history – last N analysis run summaries. */
export interface AnalysisRunSummary {
  at: number;
  conflict: string;
  escalation_score?: number;
  agents?: Record<string, { duration_ms?: number; status: string; fallback_used?: boolean }>;
  error?: string;
}

/** Per-direction token counts (Haiku API: input + output). */
export interface TokenInOut {
  in: number;
  out: number;
}

export interface MonitoringErrorEntry {
  id: string;
  ts: number;
  severity: string;
  agent?: string | null;
  source?: string | null;
  conflict?: string | null;
  message: string;
  detail?: string | null;
}

export interface AgentsMonitoringResponse {
  fallback: {
    total_events: number;
    by_agent: Record<string, number>;
    last_run: { conflict: string; at: number; agents: string[]; count: number } | null;
  };
  errors: MonitoringErrorEntry[];
  cost: {
    provider?: string;
    model?: string;
    month_budget_usd?: number;
    month_spent_usd?: number;
    month_input_tokens?: number;
    month_output_tokens?: number;
    month_by_agent?: Record<string, TokenInOut>;
    last_run?: {
      input_tokens: number;
      output_tokens: number;
      estimated_cost_usd: number;
      by_agent: Record<string, TokenInOut>;
    };
    daily?: Array<{
      day: string;
      spend_usd: number;
      input_tokens: number;
      output_tokens: number;
      by_agent: Record<string, TokenInOut>;
    }>;
    today?: {
      day: string;
      spend_usd: number;
      input_tokens: number;
      output_tokens: number;
      by_agent: Record<string, TokenInOut>;
    } | null;
  };
}

/** GET /api/agents/monitoring – fallback stats, error log, Haiku cost/tokens (in-memory). */
export async function getAgentsMonitoring(): Promise<AgentsMonitoringResponse | null> {
  try {
    const res = await apiFetch(apiUrl("agents/monitoring"), { method: "GET", timeoutMs: 15_000 });
    if (!res.ok) return null;
    return (await res.json()) as AgentsMonitoringResponse;
  } catch {
    return null;
  }
}

/** GET /api/status – per-agent heartbeat, 24h error rate, Haiku quota slice (process lifetime). */
export interface AgentsOpsHeartbeatRow {
  at: number;
  at_iso: string;
  conflict?: string;
  outcome?: string;
  duration_ms?: number;
  sources_ok_ratio?: number | null;
}

export interface AgentsOpsAgentRow {
  agent: string;
  division: string;
  last_run: AgentsOpsHeartbeatRow | null;
  last_successful_run: AgentsOpsHeartbeatRow | null;
  error_rate_24h: number | null;
  runs_24h_sample: number;
  quota: {
    haiku_month_tokens?: TokenInOut | null;
    haiku_last_run_tokens?: TokenInOut | null;
  };
}

export interface AgentsOpsStatusResponse {
  generated_at: number;
  generated_at_iso: string;
  window_error_rate_sec: number;
  agents: AgentsOpsAgentRow[];
  anthropic_haiku_global: {
    month_budget_usd?: number;
    month_spent_usd?: number;
    model?: string;
  };
  quota_note: string;
}

export async function getAgentsOpsStatus(): Promise<AgentsOpsStatusResponse | null> {
  try {
    const res = await apiFetch(`${getApiBase()}/api/status`, { method: "GET", timeoutMs: 15_000 });
    if (!res.ok) return null;
    return (await res.json()) as AgentsOpsStatusResponse;
  } catch {
    return null;
  }
}

export async function getAgentsHistory(limit = 20): Promise<{ runs: AnalysisRunSummary[] } | null> {
  try {
    const res = await apiFetch(apiUrl("agents/history", { limit }), { method: "GET", timeoutMs: DEFAULT_FETCH_TIMEOUT_MS });
    if (!res.ok) return null;
    return (await res.json()) as { runs: AnalysisRunSummary[] };
  } catch {
    return null;
  }
}

/** GET /api/agents/status – per-agent status from last analysis. */
export async function getAgentsStatus(): Promise<Record<string, unknown> | null> {
  try {
    const res = await apiFetch(apiUrl("agents/status"), { method: "GET", timeoutMs: DEFAULT_FETCH_TIMEOUT_MS });
    if (!res.ok) return null;
    const data = await res.json();
    return typeof data === "object" && data !== null ? data : null;
  } catch {
    return null;
  }
}

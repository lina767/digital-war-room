import { apiFetch, apiUrl } from "./client";

export interface ProvenanceIndexEntry {
  agent: string;
  fetched_at?: string;
  duration_ms?: number;
  sources_total?: number;
  sources_ok?: number;
  data_confidence?: string;
  processing_steps_count?: number;
}

export interface AnalyzeResponse {
  conflict: string;
  analysis_run_id?: string;
  provenance_index?: ProvenanceIndexEntry[];
  escalation_score?: number;
  threat_level?: string;
  key_findings?: string[];
  key_findings_context?: string[];
  key_findings_confidence?: string[];
  implications?: Array<{
    kind?: string;
    title?: string;
    rationale?: string;
    confidence?: string;
    source_refs?: string[];
  }>;
  trends?: Record<string, unknown>;
  anomalies_rollup?: Array<Record<string, unknown>>;
  root_cause_suggestions?: Array<{ signal: string; likely_cause: string; confidence?: string }>;
  corroborated_patterns?: Array<{
    pattern_id?: string;
    summary?: string;
    agent_ids?: string[];
    evidence?: Array<{ agent: string; snippet_or_ref?: string }>;
  }>;
  scenarios?: { description: string; probability: number }[];
  summary?: string;
  briefing_interpretation?: string;
  briefing_interpretation_meta?: { mode?: string; model?: string | null };
  narrative_story?: string;
  finint?: Record<string, unknown>;
  sigint?: Record<string, unknown>;
  news?: Record<string, unknown>;
  geoint?: Record<string, unknown>;
  socmint?: Record<string, unknown>;
  techint?: Record<string, unknown>;
  cyber?: Record<string, unknown>;
  energy?: Record<string, unknown>;
  diplo?: Record<string, unknown>;
  proximity?: Record<string, unknown>;
  predictive?: Record<string, unknown>;
  compliance?: Record<string, unknown>;
  pattern_flags?: Array<Record<string, unknown>>;
  cross_validation?: Record<string, unknown>;
  [key: string]: unknown;
}

/** Analysis can take 1–2 min (6 agents + LLM). Use long timeout. */
export const ANALYSIS_TIMEOUT_MS = 180_000;

/** Timeout for fetching cached analysis (e.g. cold start on Railway). */
export const LATEST_ANALYSIS_TIMEOUT_MS = 22_000;

/** GET /api/analyze/status – cached, running, `at`, and optional last error. */
export async function getAnalyzeStatus(
  conflict: string,
): Promise<{ cached: boolean; running?: boolean; at?: number; error?: string } | null> {
  try {
    const res = await apiFetch(apiUrl("analyze/status", { conflict }), {
      method: "GET",
      timeoutMs: 10_000,
    });
    if (!res.ok) return null;
    const raw = (await res.json()) as { cached?: boolean; running?: boolean; at?: number; error?: string };
    return { cached: raw?.cached ?? false, running: raw?.running, at: raw?.at, error: raw?.error };
  } catch {
    return null;
  }
}

/** GET /api/analyze/timeline – escalation score over time (one point per analysis run). */
export interface EscalationTimelinePoint {
  at: number;
  escalation_score: number;
  datetime_iso?: string;
  hour?: string;
  label?: string;
  label_with_date?: string;
}

export async function getEscalationTimeline(conflict: string): Promise<{ conflict: string; points: EscalationTimelinePoint[] } | null> {
  try {
    const res = await apiFetch(apiUrl("analyze/timeline", { conflict }), { method: "GET" });
    if (!res.ok) return null;
    const raw = (await res.json()) as { conflict?: string; points?: EscalationTimelinePoint[] };
    return { conflict: raw.conflict ?? conflict, points: raw.points ?? [] };
  } catch {
    return null;
  }
}

const OFFLINE_CACHE_KEY_PREFIX = "dwr:latest:";

export interface LatestAnalysisResult {
  data: AnalyzeResponse | null;
  fromCache: boolean;
}

/** GET last cached analysis (from auto-run every 6 hours). No analysis is run. Uses IndexedDB when offline. */
export async function getLatestAnalysis(conflict: string): Promise<LatestAnalysisResult> {
  const cacheKey = `${OFFLINE_CACHE_KEY_PREFIX}${conflict}`;
  try {
    const res = await apiFetch(apiUrl("analyze/latest", { conflict }), {
      method: "GET",
      timeoutMs: LATEST_ANALYSIS_TIMEOUT_MS,
    });
    if (res.status === 404 || res.status === 204) return { data: null, fromCache: false };
    if (!res.ok) return { data: null, fromCache: false };
    const raw = await res.json();
    if (raw == null) return { data: null, fromCache: false };
    const data = normalizeAnalysisResponse(raw as Record<string, unknown>);
    if (data && typeof indexedDB !== "undefined") {
      const { setCached } = await import("@/lib/offlineCache");
      setCached(cacheKey, data, 60 * 60 * 24);
    }
    return { data, fromCache: false };
  } catch {
    if (typeof indexedDB !== "undefined") {
      const { getCached } = await import("@/lib/offlineCache");
      const cached = await getCached<AnalyzeResponse>(cacheKey);
      if (cached) return { data: cached, fromCache: true };
    }
    return { data: null, fromCache: false };
  }
}

/** Response from POST /api/analyze/refresh when analysis is started in background. */
export interface TriggerRefreshResponse {
  status: string;
  conflict: string;
  message?: string;
}

/** POST /api/analyze/refresh – trigger a background analysis. Returns body on success; throws on network error or non-2xx. */
export async function triggerRefreshAnalysis(conflict: string): Promise<TriggerRefreshResponse> {
  try {
    const res = await apiFetch(apiUrl("analyze/refresh", { conflict }), {
      method: "POST",
      timeoutMs: 15_000,
    });
    const body = (await res.json().catch(() => ({}))) as TriggerRefreshResponse & { error?: string };
    if (!res.ok) {
      const msg = body?.error ?? `HTTP ${res.status}`;
      throw new Error(msg);
    }
    if (body?.status !== "started" && body?.status !== "ok") {
      throw new Error(body?.error ?? "Analysis did not start");
    }
    return body;
  } catch (e) {
    if (e instanceof Error) throw e;
    throw new Error("Request failed");
  }
}

function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

/** Normalize backend response: ensure top-level and nested shapes match frontend (e.g. articles with publishedAt). Exported for WebSocket use. */
export function normalizeAnalysisResponse(raw: Record<string, unknown>): AnalyzeResponse {
  const out = { ...raw } as AnalyzeResponse;
  const news = raw.news as Record<string, unknown> | undefined;
  if (news) {
    (out as Record<string, unknown>).news = {
      ...news,
      articles: asArray<Record<string, unknown>>(news.articles).map((a) => ({
        title: a.title,
        url: a.url,
        source: a.source,
        publishedAt: a.publishedAt ?? a.published_at,
        sentiment_label: a.sentiment_label,
        sentiment_score: a.sentiment_score,
      })),
    };
  }
  if (Array.isArray(raw.key_findings)) {
    out.key_findings = raw.key_findings.map((f: unknown) =>
      typeof f === "string" ? f : (f && typeof f === "object" && "text" in f ? String((f as { text: unknown }).text) : String(f))
    );
  }
  if (Array.isArray(raw.key_findings_context)) {
    out.key_findings_context = raw.key_findings_context.map((c: unknown) => (typeof c === "string" ? c : String(c ?? "")));
  }
  if (Array.isArray(raw.key_findings_confidence)) {
    out.key_findings_confidence = raw.key_findings_confidence.map((c: unknown) =>
      typeof c === "string" ? c : String(c ?? "medium"),
    );
  }
  if (Array.isArray(raw.root_cause_suggestions)) {
    const mapped = raw.root_cause_suggestions
      .map((x: unknown) => {
        if (!x || typeof x !== "object") return null;
        const o = x as Record<string, unknown>;
        const signal = typeof o.signal === "string" ? o.signal.trim() : "";
        const likely_cause = typeof o.likely_cause === "string" ? o.likely_cause.trim() : "";
        if (!signal || !likely_cause) return null;
        const confidence = typeof o.confidence === "string" ? o.confidence.trim().toLowerCase() : undefined;
        return {
          signal,
          likely_cause,
          ...(confidence && ["high", "medium", "low"].includes(confidence) ? { confidence } : {}),
        };
      })
      .filter(Boolean) as Array<{ signal: string; likely_cause: string; confidence?: string }>;
    (out as Record<string, unknown>).root_cause_suggestions = mapped;
  }
  if (Array.isArray(raw.scenarios)) {
    out.scenarios = raw.scenarios.map((s: unknown) => {
      const o = s as Record<string, unknown>;
      return {
        description: typeof o?.description === "string" ? o.description : String(o?.description ?? ""),
        probability: typeof o?.probability === "number" ? o.probability : 0,
      };
    });
  }
  if (typeof raw.summary === "string") out.summary = raw.summary;
  if (typeof raw.briefing_interpretation === "string") out.briefing_interpretation = raw.briefing_interpretation;
  if (raw.briefing_interpretation_meta && typeof raw.briefing_interpretation_meta === "object") {
    (out as Record<string, unknown>).briefing_interpretation_meta = raw.briefing_interpretation_meta;
  }
  if (typeof raw.narrative_story === "string") out.narrative_story = raw.narrative_story;
  (out as Record<string, unknown>).pattern_flags = asArray(raw.pattern_flags);
  (out as Record<string, unknown>).alerts = asArray(raw.alerts);
  const geoint = raw.geoint as Record<string, unknown> | undefined;
  if (geoint) {
    (out as Record<string, unknown>).geoint = {
      ...geoint,
      anomalies: asArray<Record<string, unknown>>(geoint.anomalies).map((a) => {
        const latRaw = a.latitude ?? a.lat;
        const lonRaw = a.longitude ?? a.lon;
        const lat = typeof latRaw === "number" ? latRaw : Number(latRaw);
        const lon = typeof lonRaw === "number" ? lonRaw : Number(lonRaw);
        const frp = typeof a.frp === "number" ? a.frp : Number(a.frp) || 0;
        const classification =
          typeof a.classification === "string"
            ? a.classification
            : typeof a.type === "string"
              ? a.type
              : "";
        return {
          ...a,
          latitude: lat,
          longitude: lon,
          frp,
          confidence: typeof a.confidence === "string" ? a.confidence : String(a.confidence ?? ""),
          classification,
        };
      }),
    };
  }
  const sigint = raw.sigint as Record<string, unknown> | undefined;
  if (sigint) {
    const targetTracks = asObject(sigint.target_tracks);
    (out as Record<string, unknown>).sigint = {
      ...sigint,
      aircraft: asArray(sigint.aircraft),
      ships: asArray(sigint.ships),
      conflict_reports: asArray(sigint.conflict_reports),
      alerts: asArray(sigint.alerts),
      target_tracks: targetTracks,
    };
  }
  const diplo = raw.diplo as Record<string, unknown> | undefined;
  if (diplo) {
    (out as Record<string, unknown>).diplo = {
      ...diplo,
      un_icj_news: asArray(diplo.un_icj_news),
    };
  }
  const finint = raw.finint as Record<string, unknown> | undefined;
  if (finint) {
    (out as Record<string, unknown>).finint = {
      ...finint,
      polymarket: asArray(finint.polymarket),
    };
  }
  const pentagon = raw.pentagon as Record<string, unknown> | undefined;
  if (pentagon) {
    (out as Record<string, unknown>).pentagon = {
      ...pentagon,
      venues: asArray(pentagon.venues),
    };
  }
  const chokepoint = raw.chokepoint as Record<string, unknown> | undefined;
  if (chokepoint) {
    (out as Record<string, unknown>).chokepoint = {
      ...chokepoint,
      chokepoints: asArray(chokepoint.chokepoints),
    };
  }
  const proximity = raw.proximity as Record<string, unknown> | undefined;
  if (proximity) {
    (out as Record<string, unknown>).proximity = {
      ...proximity,
      evidence: asArray(proximity.evidence),
    };
  }
  const compliance = raw.compliance as Record<string, unknown> | undefined;
  if (compliance) {
    (out as Record<string, unknown>).compliance = {
      ...compliance,
      geofencing_alerts: asArray(compliance.geofencing_alerts),
      ais_anomalies: asArray(compliance.ais_anomalies),
      ofac_recent_actions: asArray(compliance.ofac_recent_actions),
    };
  }
  (out as Record<string, unknown>).implications = asArray(raw.implications);
  (out as Record<string, unknown>).trends = asObject(raw.trends);
  (out as Record<string, unknown>).anomalies_rollup = asArray(raw.anomalies_rollup);
  return out;
}

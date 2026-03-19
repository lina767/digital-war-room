/**
 * Backend API base URL for REST and WebSocket.
 * Set VITE_API_URL in .env (e.g. http://localhost:8000) for local backend.
 */
export function getApiBase(): string {
  const env = import.meta.env.VITE_API_URL as string | undefined;
  if (env) return env.replace(/\/$/, "");
  if (typeof window !== "undefined") return window.location.origin;
  return "http://localhost:8000";
}

export function getWsUrl(path: string): string {
  const base = getApiBase();
  return base.replace(/^http/, "ws") + path;
}

/** Per-source fetch result (backend agents telemetry). */
export interface SourceResult {
  name: string;
  status: "ok" | "degraded" | "error";
  fetched_at?: string;
  duration_ms?: number;
  record_count?: number;
  error?: string;
  cached?: boolean;
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
  fallback_used?: boolean;
  error_summary?: string | null;
}

export interface AnalyzeResponse {
  conflict: string;
  escalation_score?: number;
  threat_level?: string;
  key_findings?: string[];
  key_findings_context?: string[];
  corroborated_patterns?: Array<{
    pattern_id?: string;
    summary?: string;
    agent_ids?: string[];
    evidence?: Array<{ agent: string; snippet_or_ref?: string }>;
  }>;
  scenarios?: { description: string; probability: number }[];
  summary?: string;
  finint?: Record<string, unknown>;
  sigint?: Record<string, unknown>;
  news?: Record<string, unknown>;
  geoint?: Record<string, unknown>;
  socmint?: Record<string, unknown>;
  techint?: Record<string, unknown>;
  cyber?: Record<string, unknown>;
  energy?: Record<string, unknown>;
  protest?: Record<string, unknown>;
  diplo?: Record<string, unknown>;
  proximity?: Record<string, unknown>;
  predictive?: Record<string, unknown>;
  compliance?: Record<string, unknown>;
  [key: string]: unknown;
}

/** Analysis can take 1–2 min (6 agents + LLM). Use long timeout. */
export const ANALYSIS_TIMEOUT_MS = 180_000;

/** Timeout for fetching cached analysis (e.g. cold start on Railway). */
export const LATEST_ANALYSIS_TIMEOUT_MS = 22_000;

const DEFAULT_FETCH_TIMEOUT_MS = 15_000;

/** GET /api/analyze/status – cached, at, and optional error from last failed run. */
export async function getAnalyzeStatus(conflict: string): Promise<{ cached: boolean; at?: number; error?: string } | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch(
      `${getApiBase()}/api/analyze/status?conflict=${encodeURIComponent(conflict)}`,
      { method: "GET", signal: controller.signal }
    );
    clearTimeout(timeoutId);
    if (!res.ok) return null;
    const raw = (await res.json()) as { cached?: boolean; at?: number; error?: string };
    return { cached: raw?.cached ?? false, at: raw?.at, error: raw?.error };
  } catch {
    clearTimeout(timeoutId);
    return null;
  }
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
    const res = await fetch(`${getApiBase()}/api/agents/health`);
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
  agents?: Record<string, { duration_ms?: number; status: string }>;
  error?: string;
}
export async function getAgentsHistory(limit = 20): Promise<{ runs: AnalysisRunSummary[] } | null> {
  try {
    const res = await fetch(`${getApiBase()}/api/agents/history?limit=${limit}`);
    if (!res.ok) return null;
    return (await res.json()) as { runs: AnalysisRunSummary[] };
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
  /** Exact completion time with date (e.g. "15.03. 14:35"). */
  label_with_date?: string;
}

export async function getEscalationTimeline(conflict: string): Promise<{ conflict: string; points: EscalationTimelinePoint[] } | null> {
  try {
    const res = await fetch(
      `${getApiBase()}/api/analyze/timeline?conflict=${encodeURIComponent(conflict)}`,
      { method: "GET" }
    );
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
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), LATEST_ANALYSIS_TIMEOUT_MS);
  try {
    const res = await fetch(
      `${getApiBase()}/api/analyze/latest?conflict=${encodeURIComponent(conflict)}`,
      { method: "GET", signal: controller.signal }
    );
    clearTimeout(timeoutId);
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
    clearTimeout(timeoutId);
    if (typeof indexedDB !== "undefined") {
      const { getCached } = await import("@/lib/offlineCache");
      const cached = await getCached<AnalyzeResponse>(cacheKey);
      if (cached) return { data: cached, fromCache: true };
    }
    return { data: null, fromCache: false };
  }
}

/** Response from GET /api/analyze/refresh when analysis is started in background. */
export interface TriggerRefreshResponse {
  status: string;
  conflict: string;
  message?: string;
}

/** GET /api/analyze/refresh – trigger a background analysis. Returns body on success; throws on network error or non-2xx. */
export async function triggerRefreshAnalysis(conflict: string): Promise<TriggerRefreshResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15_000);
  try {
    const res = await fetch(
      `${getApiBase()}/api/analyze/refresh?conflict=${encodeURIComponent(conflict)}`,
      { method: "GET", signal: controller.signal }
    );
    clearTimeout(timeoutId);
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
    clearTimeout(timeoutId);
    if (e instanceof Error) throw e;
    throw new Error("Request failed");
  }
}

/** POST /api/newsletter/subscribe – subscribe to daily briefing (double opt-in). */
export async function newsletterSubscribe(body: { email: string; conflict?: string }): Promise<{ message: string; conflict: string }> {
  const res = await fetch(`${getApiBase()}/api/newsletter/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: body.email, conflict: body.conflict ?? "Iran" }),
  });
  const data = (await res.json().catch(() => ({}))) as { message?: string; conflict?: string; error?: string };
  if (!res.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
  return { message: data.message ?? "Subscribed.", conflict: data.conflict ?? "Iran" };
}

/** GET /api/newsletter/confirm?token=... – confirm subscription (double opt-in). */
export async function newsletterConfirm(token: string): Promise<{ message: string }> {
  const res = await fetch(`${getApiBase()}/api/newsletter/confirm?${new URLSearchParams({ token })}`);
  const data = (await res.json().catch(() => ({}))) as { message?: string; error?: string };
  if (!res.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
  return { message: data.message ?? "Confirmed." };
}

/** GET /api/newsletter/unsubscribe?token=... – unsubscribe. */
export async function newsletterUnsubscribe(token: string): Promise<{ message: string }> {
  const res = await fetch(`${getApiBase()}/api/newsletter/unsubscribe?${new URLSearchParams({ token })}`);
  const data = (await res.json().catch(() => ({}))) as { message?: string; error?: string };
  if (!res.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
  return { message: data.message ?? "Unsubscribed." };
}

/** Normalize backend response: ensure top-level and nested shapes match frontend (e.g. articles with publishedAt). Exported for WebSocket use. */
export function normalizeAnalysisResponse(raw: Record<string, unknown>): AnalyzeResponse {
  const out = { ...raw } as AnalyzeResponse;
  const news = raw.news as Record<string, unknown> | undefined;
  if (news && Array.isArray(news.articles)) {
    (out as Record<string, unknown>).news = {
      ...news,
      articles: (news.articles as Record<string, unknown>[]).map((a) => ({
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
  return out;
}

/** Conflict event for heatmap (ACLED lat/lon + intensity). */
export interface ConflictEventForHeatmap {
  lat: number;
  lon: number;
  intensity: number;
  source?: string;
  event_type?: string | null;
  fatalities?: number;
  actor1?: string | null;
  actor2?: string | null;
  notes?: string | null;
  event_date?: string | null;
}

/** GET /api/conflict-events – events with lat, lon, intensity for heatmap layer (ACLED). */
export async function getConflictEvents(
  conflict: string,
  limit = 200
): Promise<{ events: ConflictEventForHeatmap[]; conflict: string } | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15_000);
  try {
    const res = await fetch(
      `${getApiBase()}/api/conflict-events?conflict=${encodeURIComponent(conflict)}&limit=${limit}`,
      { method: "GET", signal: controller.signal }
    );
    clearTimeout(timeoutId);
    if (!res.ok) return null;
    const raw = (await res.json()) as { events?: ConflictEventForHeatmap[]; conflict?: string };
    const events = Array.isArray(raw?.events) ? raw.events : [];
    return { events, conflict: raw?.conflict ?? conflict };
  } catch {
    clearTimeout(timeoutId);
    return null;
  }
}

// ── GreyNoise Emerging Threats ─────────────────────────────────────────────

export interface GreynoiseEmergingThreat {
  tag: string;
  category: string;
  direction: "inbound" | "outbound";
  scan_volume: number;
  scan_volume_change?: number | null;
  priority: "low" | "medium" | "high";
  cve_id?: string | null;
  cvss_score?: number | null;
  products?: string[] | null;
  source_countries: string[];
  destination_countries: string[];
  weight: number;
}

export interface GreynoiseTopIp {
  ip: string;
  direction: string;
  classification?: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface GreynoiseResult {
  conflict: string;
  emerging_threats: GreynoiseEmergingThreat[];
  greynoise_score: number;
  absolute_score: number;
  delta_score: number;
  trend: "rising" | "stable" | "falling";
  alerts: string[];
  summary: string;
  score_confidence: { level: string; sources_ok?: string[]; sources_missing?: string[] };
  fetched_at: string;
  outbound_count: number;
  inbound_count: number;
  top_tags_outbound: Array<{ tag: string; count: number }>;
  top_tags_inbound: Array<{ tag: string; count: number }>;
  pending_tags: string[];
  top_ips?: GreynoiseTopIp[];
}

export interface GreynoiseTrendPoint {
  timestamp: string;
  greynoise_score: number;
  absolute_score: number;
  total_events: number;
}

export interface GreynoiseTrendResponse {
  conflict: string;
  days: number;
  trend: GreynoiseTrendPoint[];
}

/** GET /api/greynoise/{conflict} – latest snapshot. */
export async function fetchGreynoiseThreats(conflict: string): Promise<GreynoiseResult | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15_000);
  try {
    const res = await fetch(
      `${getApiBase()}/api/greynoise/${encodeURIComponent(conflict)}`,
      { method: "GET", signal: controller.signal },
    );
    clearTimeout(timeoutId);
    if (!res.ok) return null;
    return (await res.json()) as GreynoiseResult;
  } catch {
    clearTimeout(timeoutId);
    return null;
  }
}

/** GET /api/greynoise/{conflict}/trend?days=N – score time series. */
export async function fetchGreynoiseTrend(conflict: string, days = 7): Promise<GreynoiseTrendResponse | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch(
      `${getApiBase()}/api/greynoise/${encodeURIComponent(conflict)}/trend?days=${days}`,
      { method: "GET", signal: controller.signal },
    );
    clearTimeout(timeoutId);
    if (!res.ok) return null;
    return (await res.json()) as GreynoiseTrendResponse;
  } catch {
    clearTimeout(timeoutId);
    return null;
  }
}

/** Theater map event (unified FIRMS + ACLED + ACLED-Aggregated) for type-specific icons. */
export interface TheaterEvent {
  lat: number;
  lon: number;
  event_type: "airstrike" | "missile" | "drone" | "explosion" | "naval" | "fire" | "other";
  source?: string;
  confidence?: string;
  label?: string;
  /** Total fatalities (ACLED). */
  fatalities?: number;
  /** Civilian deaths. */
  deaths_civilians?: number;
  /** Military/actor deaths. */
  deaths_a?: number;
  deaths_b?: number;
  /** Actors (ACLED). */
  actor1?: string;
  actor2?: string;
  side_a?: string;
  side_b?: string;
  /** Date of event. */
  event_date?: string;
  date_start?: string;
  /** Additional context / reporting. */
  notes?: string;
  /** Link to imagery (EO Browser) or source. */
  url?: string;
  /** ACLED sub-event type (e.g. Shelling, Armed clash). */
  sub_event_type?: string;
  /** Aggregated: number of events in the weekly period. */
  events_count?: number;
  /** Country (aggregated data). */
  country?: string;
  /** Admin1 region/province (aggregated data). */
  admin1?: string;
}

// ── Agents status ───────────────────────────────────────────────────────────

/** GET /api/agents/status – per-agent status from last analysis. */
export async function getAgentsStatus(): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${getApiBase()}/api/agents/status`, {
      signal: AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return typeof data === "object" && data !== null ? data : null;
  } catch {
    return null;
  }
}

// ── Compliance ──────────────────────────────────────────────────────────────

export interface ZonesResponse {
  sanctions_zones: Array<{ name?: string; zone_type?: string; source?: string }>;
  all_zones: Array<{ name?: string; zone_type?: string; source?: string }>;
}

/** GET /api/compliance/zones. */
export async function getComplianceZones(): Promise<ZonesResponse | null> {
  try {
    const res = await fetch(`${getApiBase()}/api/compliance/zones`, {
      signal: AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    return (await res.json()) as ZonesResponse;
  } catch {
    return null;
  }
}

export interface RouteScreeningBody {
  route_label: string;
  waypoints: Array<{ label: string; lat: number; lon: number; country_code?: string; port_type?: string }>;
}

export interface RouteScreeningResult {
  route_label: string;
  waypoints: Array<{ label: string; lat: number; lon: number }>;
  zone_hits: Array<{ waypoint: string; zone_name: string; zone_type: string; zone_source?: string }>;
  suspicious_hops?: Array<{ waypoint: string; country_code: string; hub_label: string; condition: string; rationale?: string }>;
  touches_sanctions_zone?: boolean;
  disclaimer?: string;
  summary?: string;
}

/** POST /api/compliance/route-screening. */
export async function postComplianceRouteScreening(
  body: RouteScreeningBody
): Promise<RouteScreeningResult> {
  const res = await fetch(`${getApiBase()}/api/compliance/route-screening`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as RouteScreeningResult;
}

// ── Documents ───────────────────────────────────────────────────────────────

export interface DocumentItem {
  id?: string;
  url?: string;
  source?: string;
  conflict?: string;
  ingested_at?: string;
  [key: string]: unknown;
}

/** GET /api/documents. */
export async function getDocuments(): Promise<DocumentItem[]> {
  try {
    const res = await fetch(`${getApiBase()}/api/documents`, {
      signal: AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return [];
    const raw = await res.json();
    if (Array.isArray(raw)) return raw as DocumentItem[];
    if (raw && Array.isArray((raw as { documents?: unknown }).documents)) {
      return (raw as { documents: DocumentItem[] }).documents;
    }
    return [];
  } catch {
    return [];
  }
}

/** POST /api/documents/ingest. */
export async function postDocumentsIngest(body: {
  url: string;
  source?: string;
  conflict?: string;
}): Promise<void> {
  const res = await fetch(`${getApiBase()}/api/documents/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(await res.text());
}

/** POST /api/documents/qa. */
export async function postDocumentsQa(body: {
  question: string;
  conflict?: string;
}): Promise<Record<string, unknown>> {
  const res = await fetch(`${getApiBase()}/api/documents/qa`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as Record<string, unknown>;
}

// ── Chokepoints ─────────────────────────────────────────────────────────────

/** GET /api/chokepoints/overrides. */
export async function getChokepointOverrides(): Promise<Record<string, string>> {
  try {
    const res = await fetch(`${getApiBase()}/api/chokepoints/overrides`, {
      signal: AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return {};
    const next = (await res.json()) as Record<string, string> | null;
    return next ?? {};
  } catch {
    return {};
  }
}

/** POST /api/chokepoints/overrides. */
export async function postChokepointOverrides(
  overrides: Record<string, string>
): Promise<Record<string, string>> {
  const res = await fetch(`${getApiBase()}/api/chokepoints/overrides`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(overrides),
    signal: AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(await res.text());
  const updated = (await res.json()) as Record<string, string>;
  return updated ?? {};
}

// ── Theater events ──────────────────────────────────────────────────────────

/** GET /api/theater-events – unified events for Theater Map layer (Iran etc.). */
export async function getTheaterEvents(
  conflict: string,
  limit = 400
): Promise<{ events: TheaterEvent[]; conflict: string } | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 20_000);
  try {
    const res = await fetch(
      `${getApiBase()}/api/theater-events?conflict=${encodeURIComponent(conflict)}&limit=${limit}`,
      { method: "GET", signal: controller.signal }
    );
    clearTimeout(timeoutId);
    if (!res.ok) return null;
    const raw = (await res.json()) as { events?: TheaterEvent[]; conflict?: string };
    const events = Array.isArray(raw?.events) ? raw.events : [];
    return { events, conflict: raw?.conflict ?? conflict };
  } catch {
    clearTimeout(timeoutId);
    return null;
  }
}

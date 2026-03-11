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

export interface AnalyzeResponse {
  conflict: string;
  escalation_score?: number;
  threat_level?: string;
  key_findings?: string[];
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
  [key: string]: unknown;
}

/** Analysis can take 1–2 min (6 agents + LLM). Use long timeout. */
const ANALYSIS_TIMEOUT_MS = 180_000;

/** Timeout für Abruf der gecachten Analyse (Cold Start z. B. Railway). */
const LATEST_ANALYSIS_TIMEOUT_MS = 22_000;

/** GET /api/analyze/status – leichtgewichtig, um Backend erreichbar vs. kein Cache zu unterscheiden. */
export async function getAnalyzeStatus(conflict: string): Promise<{ cached: boolean; at?: number } | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch(
      `${getApiBase()}/api/analyze/status?conflict=${encodeURIComponent(conflict)}`,
      { method: "GET", signal: controller.signal }
    );
    clearTimeout(timeoutId);
    if (!res.ok) return null;
    const raw = (await res.json()) as { cached?: boolean; at?: number };
    return { cached: raw?.cached ?? false, at: raw?.at };
  } catch {
    clearTimeout(timeoutId);
    return null;
  }
}

/** GET last cached analysis (from auto-run every 6 hours). No analysis is run. */
export async function getLatestAnalysis(conflict: string): Promise<AnalyzeResponse | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), LATEST_ANALYSIS_TIMEOUT_MS);
  try {
    const res = await fetch(
      `${getApiBase()}/api/analyze/latest?conflict=${encodeURIComponent(conflict)}`,
      { method: "GET", signal: controller.signal }
    );
    clearTimeout(timeoutId);
    if (res.status === 404 || res.status === 204) return null;
    if (!res.ok) return null;
    const raw = await res.json();
    if (raw == null) return null;
    return normalizeAnalysisResponse(raw as Record<string, unknown>);
  } catch {
    clearTimeout(timeoutId);
    return null;
  }
}

/**
 * Holt die aktuelle Analyse aus dem Cache (keine neue Analyse).
 * Analysen laufen alle 6 Stunden im Backend. Bei 503: noch kein Cache.
 */
export async function runAnalysis(conflict: string): Promise<AnalyzeResponse> {
  try {
    const res = await fetch(`${getApiBase()}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conflict }),
    });
    if (res.status === 503) {
      const body = await res.json().catch(() => ({}));
      const msg = (body as { error?: string })?.error ?? "No cached analysis yet. Analysis runs automatically every 6 hours.";
      throw new Error(msg);
    }
    if (!res.ok) throw new Error(`Analysis failed: ${res.status} ${res.statusText}`);
    const raw = await res.json();
    return normalizeAnalysisResponse(raw);
  } catch (e) {
    if (e instanceof Error) throw e;
    throw new Error(String(e));
  }
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

/** Theater map event (unified FIRMS + ACLED + UCDP) for type-specific icons. */
export interface TheaterEvent {
  lat: number;
  lon: number;
  event_type: "airstrike" | "missile" | "drone" | "explosion" | "naval" | "fire" | "other";
  source?: string;
  confidence?: string;
  label?: string;
}

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

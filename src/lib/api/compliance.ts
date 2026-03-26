import { apiFetch, apiUrl, DEFAULT_FETCH_TIMEOUT_MS, readOkJson } from "./client";

export interface ZonesResponse {
  sanctions_zones: Array<{ name?: string; zone_type?: string; source?: string }>;
  all_zones: Array<{ name?: string; zone_type?: string; source?: string }>;
}

/** GET /api/compliance/zones. */
export async function getComplianceZones(): Promise<ZonesResponse | null> {
  try {
    const res = await apiFetch(apiUrl("compliance/zones"), {
      method: "GET",
      timeoutMs: DEFAULT_FETCH_TIMEOUT_MS,
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
export async function postComplianceRouteScreening(body: RouteScreeningBody): Promise<RouteScreeningResult> {
  const res = await apiFetch(apiUrl("compliance/route-screening"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: DEFAULT_FETCH_TIMEOUT_MS,
  });
  return readOkJson<RouteScreeningResult>(res);
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
    const res = await apiFetch(apiUrl("documents"), {
      method: "GET",
      timeoutMs: DEFAULT_FETCH_TIMEOUT_MS,
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
export async function postDocumentsIngest(body: { url: string; source?: string; conflict?: string }): Promise<void> {
  const res = await apiFetch(apiUrl("documents/ingest"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: DEFAULT_FETCH_TIMEOUT_MS,
  });
  if (!res.ok) throw new Error(await res.text());
}

/** POST /api/documents/qa. */
export async function postDocumentsQa(body: { question: string; conflict?: string }): Promise<Record<string, unknown>> {
  const res = await apiFetch(apiUrl("documents/qa"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: 20_000,
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as Record<string, unknown>;
}

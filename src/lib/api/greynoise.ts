import { apiFetch, apiUrl } from "./client";

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
  try {
    const res = await apiFetch(apiUrl(`greynoise/${encodeURIComponent(conflict)}`), {
      method: "GET",
      timeoutMs: 15_000,
    });
    if (!res.ok) return null;
    return (await res.json()) as GreynoiseResult;
  } catch {
    return null;
  }
}

/** GET /api/greynoise/{conflict}/trend?days=N – score time series. */
export async function fetchGreynoiseTrend(conflict: string, days = 7): Promise<GreynoiseTrendResponse | null> {
  try {
    const res = await apiFetch(apiUrl(`greynoise/${encodeURIComponent(conflict)}/trend`, { days }), {
      method: "GET",
      timeoutMs: 10_000,
    });
    if (!res.ok) return null;
    return (await res.json()) as GreynoiseTrendResponse;
  } catch {
    return null;
  }
}

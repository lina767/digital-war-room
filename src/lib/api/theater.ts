import { apiFetch, apiUrl } from "./client";

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
  limit = 200,
): Promise<{ events: ConflictEventForHeatmap[]; conflict: string } | null> {
  try {
    const res = await apiFetch(apiUrl("conflict-events", { conflict, limit }), {
      method: "GET",
      timeoutMs: 15_000,
    });
    if (!res.ok) return null;
    const raw = (await res.json()) as { events?: ConflictEventForHeatmap[]; conflict?: string };
    const events = Array.isArray(raw?.events) ? raw.events : [];
    return { events, conflict: raw?.conflict ?? conflict };
  } catch {
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
  fatalities?: number;
  deaths_civilians?: number;
  deaths_a?: number;
  deaths_b?: number;
  actor1?: string;
  actor2?: string;
  side_a?: string;
  side_b?: string;
  event_date?: string;
  date_start?: string;
  notes?: string;
  url?: string;
  sub_event_type?: string;
  events_count?: number;
  country?: string;
  admin1?: string;
}

/** GET /api/theater-events – unified events for Theater Map layer (Iran etc.). */
export async function getTheaterEvents(
  conflict: string,
  limit = 400,
): Promise<{ events: TheaterEvent[]; conflict: string } | null> {
  try {
    const res = await apiFetch(apiUrl("theater-events", { conflict, limit }), {
      method: "GET",
      timeoutMs: 20_000,
    });
    if (!res.ok) return null;
    const raw = (await res.json()) as { events?: TheaterEvent[]; conflict?: string };
    const events = Array.isArray(raw?.events) ? raw.events : [];
    return { events, conflict: raw?.conflict ?? conflict };
  } catch {
    return null;
  }
}

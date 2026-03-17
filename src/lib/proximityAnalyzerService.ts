/**
 * Proximity Analyzer Service
 * Correlates strike data (NASA FIRMS thermal anomalies) with civilian infrastructure (OSM Overpass)
 * to identify potential Human Shield scenarios. Uses Turf.js (haversine) for distances.
 */
import distance from "@turf/distance";
import { point } from "@turf/helpers";
import { getApiBase } from "./api";

// ── Types ───────────────────────────────────────────────────────────────────

export interface StrikeRecord {
  lat: number;
  lon: number;
  frp?: number;
  confidence?: string;
  type?: string;
  acquired?: string;
}

export interface CivilianFacility {
  id: string;
  name: string;
  lat: number;
  lon: number;
  amenity?: string;
  office?: string;
  tags?: Record<string, string>;
}

export type RiskLabel =
  | "CRITICAL_PROXIMITY"   // < 50 m
  | "HIGH_RISK"           // < 150 m
  | "PROBABLE_HUMAN_SHIELD" // civilian near strike AND military site within 100m of same civilian
  | "ELEVATED";           // 150–300 m (informational)

export interface ProximityEvidence {
  facilityName: string;
  facilityType: string;
  distanceMeters: number;
  riskLabel: RiskLabel;
  strikeLat: number;
  strikeLon: number;
  facilityLat: number;
  facilityLon: number;
  strikeAcquired?: string;
  summary: string;
  /** Optional 2–3 sentence "why this matters" from supervisor/agent. */
  why_it_matters?: string;
}

export interface MilitarySiteFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties?: { name?: string; type?: string };
}

/** GeoJSON FeatureCollection of suspected military sites (optional, for HUMAN_SHIELD flag). */
export interface MilitarySitesGeoJSON {
  type: "FeatureCollection";
  features: MilitarySiteFeature[];
}

const OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter";
const OVERPASS_RADIUS_M = 300;
const CRITICAL_PROXIMITY_M = 50;
const HIGH_RISK_M = 150;
const HUMAN_SHIELD_NEAR_M = 100;
const REQUEST_DELAY_MS = 1100;
/** Cap strikes to process (Overpass rate limit: ~1 req/s). Keeps run under ~20 s. */
const MAX_STRIKES_TO_PROCESS = 15;

// ── Strike data (NASA FIRMS via backend) ─────────────────────────────────────

/**
 * Fetches real-time thermal anomalies from NASA FIRMS (VIIRS_SNPP_NRT) via backend.
 * These are used as strike triggers when Liveuamap is not available.
 */
export async function fetchStrikeData(
  region: string = "middle_east",
  days: number = 3
): Promise<StrikeRecord[]> {
  const url = `${getApiBase()}/api/proximity/strikes?region=${encodeURIComponent(region)}&days=${Math.max(1, Math.min(5, days))}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(35_000) });
  if (!res.ok) throw new Error(`Strike data failed: ${res.status}`);
  const data = (await res.json()) as { strikes?: StrikeRecord[] };
  const strikes = data.strikes ?? [];
  return strikes.filter((s) => typeof s.lat === "number" && typeof s.lon === "number");
}

/**
 * Fetches IRGC tunnel / military sites GeoJSON from backend (when TUNNEL_SITES_GEOJSON_URL is set).
 * Use for Iran-focused runs to flag PROBABLE_HUMAN_SHIELD when a site is within 100m of a school/hospital.
 */
export async function fetchTunnelSites(): Promise<MilitarySitesGeoJSON | null> {
  const url = `${getApiBase()}/api/proximity/tunnel-sites`;
  const res = await fetch(url, { signal: AbortSignal.timeout(10_000) });
  if (!res.ok) return null;
  const data = (await res.json()) as MilitarySitesGeoJSON;
  if (data?.type === "FeatureCollection" && Array.isArray(data.features) && data.features.length > 0) {
    return data;
  }
  return null;
}

// ── Overpass API (civilian infrastructure) ───────────────────────────────────

/**
 * Builds Overpass QL query for civilian infrastructure within radius (meters) of a point.
 * Tags: amenity ~ school|hospital|place_of_worship; office = government.
 */
function buildOverpassQuery(lat: number, lon: number, radiusM: number): string {
  return `
[out:json][timeout:25];
(
  node(around:${radiusM},${lat},${lon})["amenity"~"school|hospital|place_of_worship"];
  way(around:${radiusM},${lat},${lon})["amenity"~"school|hospital|place_of_worship"];
  node(around:${radiusM},${lat},${lon})["office"="government"];
  way(around:${radiusM},${lat},${lon})["office"="government"];
);
out body center;
`.trim();
}

/**
 * Parses Overpass JSON response into CivilianFacility list.
 * Handles node (lat/lon) and way (center lat/lon).
 */
function parseOverpassElements(elements: Array<Record<string, unknown>>): CivilianFacility[] {
  const facilities: CivilianFacility[] = [];
  const seen = new Set<string>();

  for (const el of elements) {
    const tags = (el.tags as Record<string, string>) ?? {};
    const name = tags.name ?? tags["name:en"] ?? "Unnamed facility";
    let lat: number;
    let lon: number;

    if (el.type === "node") {
      lat = Number(el.lat);
      lon = Number(el.lon);
    } else if (el.type === "way" && el.center) {
      const c = el.center as { lat?: number; lon?: number };
      lat = Number(c.lat);
      lon = Number(c.lon);
    } else {
      continue;
    }

    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;

    const amenity = tags.amenity ?? "";
    const office = tags.office ?? "";
    const key = `${lat.toFixed(5)}-${lon.toFixed(5)}-${name}`;
    if (seen.has(key)) continue;
    seen.add(key);

    facilities.push({
      id: String(el.id ?? key),
      name,
      lat,
      lon,
      amenity: amenity || undefined,
      office: office || undefined,
      tags,
    });
  }
  return facilities;
}

/**
 * Queries OpenStreetMap Overpass API for civilian infrastructure within radius of (lat, lon).
 * Rate-limited: use with delay between calls to avoid 429.
 */
export async function fetchOverpassContext(lat: number, lon: number): Promise<CivilianFacility[]> {
  const query = buildOverpassQuery(lat, lon, OVERPASS_RADIUS_M);
  const res = await fetch(OVERPASS_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `data=${encodeURIComponent(query)}`,
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) throw new Error(`Overpass failed: ${res.status}`);
  const json = (await res.json()) as { elements?: Array<Record<string, unknown>> };
  const elements = json.elements ?? [];
  return parseOverpassElements(elements);
}

/** Delay helper for rate-limiting Overpass requests. */
function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Correlation (Turf.js haversine) ──────────────────────────────────────────

/**
 * Returns distance in meters between two points using Turf.js (haversine).
 * GeoJSON order is [longitude, latitude].
 */
export function distanceMeters(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const from = point([lon1, lat1]);
  const to = point([lon2, lat2]);
  return distance(from, to, { units: "meters" });
}

/**
 * For a strike and a list of civilian facilities, finds the nearest facility
 * and returns distance and risk label.
 */
function nearestFacilityAndDistance(
  strikeLat: number,
  strikeLon: number,
  facilities: CivilianFacility[],
  militarySites?: MilitarySitesGeoJSON
): { facility: CivilianFacility; distanceMeters: number; riskLabel: RiskLabel } | null {
  if (facilities.length === 0) return null;

  let nearest: CivilianFacility | null = null;
  let minDist = Infinity;

  for (const f of facilities) {
    const d = distanceMeters(strikeLat, strikeLon, f.lat, f.lon);
    if (d < minDist) {
      minDist = d;
      nearest = f;
    }
  }

  if (!nearest || minDist > OVERPASS_RADIUS_M) return null;

  let riskLabel: RiskLabel = "ELEVATED";
  if (minDist < CRITICAL_PROXIMITY_M) riskLabel = "CRITICAL_PROXIMITY";
  else if (minDist < HIGH_RISK_M) riskLabel = "HIGH_RISK";

  if (militarySites?.features?.length && nearest) {
    const civilPoint = point([nearest.lon, nearest.lat]);
    for (const feat of militarySites.features) {
      const coords = feat.geometry?.coordinates;
      if (!coords || coords.length < 2) continue;
      const distToMilitary = distance(civilPoint, point(coords), { units: "meters" });
      if (distToMilitary < HUMAN_SHIELD_NEAR_M) {
        riskLabel = "PROBABLE_HUMAN_SHIELD";
        break;
      }
    }
  }

  return { facility: nearest, distanceMeters: minDist, riskLabel };
}

/**
 * Generates a short summary for the evidence card (mocked AI-style).
 */
function buildSummary(
  facilityName: string,
  distanceMeters: number,
  riskLabel: RiskLabel
): string {
  const d = Math.round(distanceMeters);
  if (riskLabel === "PROBABLE_HUMAN_SHIELD") {
    return `Strike detected within ${d}m of ${facilityName}. Suspected military site also near this facility. Probable human shield scenario.`;
  }
  if (riskLabel === "CRITICAL_PROXIMITY") {
    return `Strike detected within ${d}m of ${facilityName}. Critical proximity; high probability of collateral damage or dual-use.`;
  }
  if (riskLabel === "HIGH_RISK") {
    return `Strike detected within ${d}m of ${facilityName}. High risk of collateral damage or dual-use.`;
  }
  return `Strike detected within ${d}m of ${facilityName}. Elevated risk; monitor for collateral impact.`;
}

// ── Main analysis pipeline ──────────────────────────────────────────────────

/**
 * Runs the full Proximity Analysis via backend: strikes (NASA FIRMS), Overpass
 * (schools/hospitals/government), and optional tunnel/military sites for
 * PROBABLE_HUMAN_SHIELD. Server-side correlation; no client-side Overpass calls.
 * @param militarySites – ignored (backend fetches tunnel sites when region is middle_east/iran)
 */
export async function runProximityAnalysis(
  region: string = "middle_east",
  days: number = 3,
  _militarySites?: MilitarySitesGeoJSON | null
): Promise<ProximityEvidence[]> {
  const d = Math.max(1, Math.min(5, days));
  const url = `${getApiBase()}/api/proximity/analyze?region=${encodeURIComponent(region)}&days=${d}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(90_000) });
  if (!res.ok) throw new Error(`Proximity analyze failed: ${res.status}`);
  const data = (await res.json()) as { evidence?: ProximityEvidence[] };
  const evidence = data.evidence ?? [];
  return evidence.sort((a, b) => a.distanceMeters - b.distanceMeters);
}

import type { SigintAircraft, SigintShip } from "@/types/theaterMap";

/** Accept API quirks: numeric strings, latitude/longitude aliases. */
export function toFiniteCoord(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = parseFloat(v.trim());
    if (Number.isFinite(n)) return n;
  }
  return null;
}

/** Returns a copy with numeric lat/lon for map layers, or null if position is unusable. */
export function normalizeSigintAircraftForMap(a: SigintAircraft): SigintAircraft | null {
  const raw = a as SigintAircraft & { latitude?: unknown; longitude?: unknown };
  const lat = toFiniteCoord(raw.lat ?? raw.latitude);
  const lon = toFiniteCoord(raw.lon ?? raw.longitude);
  if (lat == null || lon == null) return null;
  return { ...a, lat, lon };
}

export function normalizeSigintShipForMap(s: SigintShip): SigintShip | null {
  const raw = s as SigintShip & { latitude?: unknown; longitude?: unknown };
  const lat = toFiniteCoord(raw.lat ?? raw.latitude);
  const lon = toFiniteCoord(raw.lon ?? raw.longitude);
  if (lat == null || lon == null) return null;
  return { ...s, lat, lon };
}

/** Rough center + zoom to frame lon/lat points (WGS84). */
export function viewStateForLonLatPoints(
  points: Array<[number, number]>,
): { longitude: number; latitude: number; zoom: number; pitch: number; bearing: number } | null {
  if (points.length === 0) return null;
  let minLat = 90;
  let maxLat = -90;
  let minLon = 180;
  let maxLon = -180;
  for (const [lon, lat] of points) {
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    minLat = Math.min(minLat, lat);
    maxLat = Math.max(maxLat, lat);
    minLon = Math.min(minLon, lon);
    maxLon = Math.max(maxLon, lon);
  }
  if (minLat > maxLat || minLon > maxLon) return null;
  const lonSpan = Math.max(maxLon - minLon, 0.25);
  const latSpan = Math.max(maxLat - minLat, 0.25);
  const pad = 1.35;
  const maxSpan = Math.max(lonSpan, latSpan) * pad;
  const zoom = Math.min(9, Math.max(2.5, Math.log2(360 / maxSpan) - 0.35));
  return {
    longitude: (minLon + maxLon) / 2,
    latitude: (minLat + maxLat) / 2,
    zoom,
    pitch: 0,
    bearing: 0,
  };
}

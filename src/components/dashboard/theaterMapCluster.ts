import type { TheaterEvent } from "@/lib/api";

export type TheaterDisplayItem =
  | { type: "event"; event: TheaterEvent }
  | { type: "cluster"; lat: number; lon: number; events: TheaterEvent[] };

const CLUSTER_MIN_POINTS = 45;

/** Grid cell size in degrees – shrinks as zoom increases so clusters split when zooming in. */
function cellSizeDegrees(zoom: number): number {
  return Math.max(0.06, 3.5 / Math.pow(zoom, 1.2));
}

function validEvents(events: TheaterEvent[]): TheaterEvent[] {
  return events.filter(
    (e) => typeof e.lat === "number" && typeof e.lon === "number" && isFinite(e.lat) && isFinite(e.lon),
  );
}

/**
 * When clustering is on and there are many points, group nearby events into one marker per grid cell.
 * Centroid = mean lat/lon; click typically zooms in so the grid refines.
 */
export function buildTheaterDisplayItems(
  events: TheaterEvent[],
  zoom: number,
  clusteringEnabled: boolean,
): TheaterDisplayItem[] {
  const valid = validEvents(events);
  if (!clusteringEnabled || valid.length <= CLUSTER_MIN_POINTS) {
    return valid.map((event) => ({ type: "event" as const, event }));
  }

  const cell = cellSizeDegrees(zoom);
  const buckets = new Map<string, TheaterEvent[]>();

  for (const e of valid) {
    const gi = Math.floor(e.lat / cell);
    const gj = Math.floor(e.lon / cell);
    const key = `${gi}:${gj}`;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key)!.push(e);
  }

  const out: TheaterDisplayItem[] = [];
  for (const [, arr] of buckets) {
    if (arr.length === 1) {
      out.push({ type: "event", event: arr[0] });
      continue;
    }
    const lat = arr.reduce((s, x) => s + x.lat, 0) / arr.length;
    const lon = arr.reduce((s, x) => s + x.lon, 0) / arr.length;
    out.push({ type: "cluster", lat, lon, events: arr });
  }
  return out;
}

export { CLUSTER_MIN_POINTS };

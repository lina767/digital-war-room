/**
 * Shared map configuration for WorldMap and TheaterMap.
 * Extracted from ConflictMap.
 */

export const GEO_URL = "https://unpkg.com/world-atlas@2.0.2/countries-110m.json";

export interface GeointAnomaly {
  latitude: number;
  longitude: number;
  frp: number;
  confidence: string;
  classification: string;
}

export interface SigintAircraft {
  flight: string;
  lat: number;
  lon: number;
  category?: string;
}

export interface SigintShip {
  name: string;
  lat: number;
  lon: number;
  type?: string;
}

export const CONFLICT_CENTERS: Record<
  string,
  { center: [number, number]; zoom: number }
> = {
  iran: { center: [53, 32], zoom: 4 },
  "us-iran": { center: [53, 28], zoom: 3.5 },
  ukraine: { center: [32, 48], zoom: 4 },
  "israel-palestine": { center: [35, 31], zoom: 5 },
  lebanon: { center: [35.8, 33.9], zoom: 5.5 },
  "taiwan-strait": { center: [120, 24], zoom: 4 },
  sudan: { center: [30, 15], zoom: 3.5 },
  yemen: { center: [46, 15], zoom: 4 },
  myanmar: { center: [96, 20], zoom: 4 },
  sahel: { center: [2, 15], zoom: 3 },
  korea: { center: [127, 37], zoom: 4.5 },
  syria: { center: [38, 35], zoom: 5 },
  drc: { center: [24, -3], zoom: 3.5 },
  ethiopia: { center: [40, 9], zoom: 4 },
};

export const THEATER_EVENT_STYLE: Record<
  string,
  { label: string; fill: string; stroke: string }
> = {
  airstrike: { label: "Airstrike", fill: "#dc2626", stroke: "#b91c1c" },
  missile: { label: "Missile", fill: "#ea580c", stroke: "#c2410c" },
  drone: { label: "Drone", fill: "#ca8a04", stroke: "#a16207" },
  explosion: { label: "Explosion", fill: "#dc2626", stroke: "#991b1b" },
  naval: { label: "Naval", fill: "#2563eb", stroke: "#1d4ed8" },
  fire: { label: "Fire", fill: "#ea580c", stroke: "#c2410c" },
  other: { label: "Other", fill: "#6b7280", stroke: "#4b5563" },
};

/**
 * Conflict keys for which SAM / Air routes / Sea lanes overlay data exists (Iran/Gulf/Levant).
 * For other conflicts, those overlays are not rendered.
 */
export const OVERLAY_CONFLICT_KEYS = [
  "iran",
  "us-iran",
  "israel-palestine",
  "lebanon",
  "yemen",
  "syria",
] as const;

export function hasOverlayDataForConflict(conflict: string | null): boolean {
  if (!conflict) return false;
  const key = matchConflict(conflict);
  return key != null && (OVERLAY_CONFLICT_KEYS as readonly string[]).includes(key);
}

/** Fuzzy match: "Iran" → "iran" */
export function matchConflict(name: string): string | null {
  if (!name) return null;
  const normalized = name
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "");
  for (const key of Object.keys(CONFLICT_CENTERS)) {
    if (
      normalized.includes(key) ||
      key.split("-").every((part) => normalized.includes(part))
    ) {
      return key;
    }
  }
  return null;
}

export const DEFAULT_WORLD_CENTER: [number, number] = [10, 20];
export const DEFAULT_WORLD_ZOOM = 1;

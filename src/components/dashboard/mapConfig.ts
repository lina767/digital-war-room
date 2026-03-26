/**
 * Shared map configuration for WorldMap and TheaterMap.
 * Extracted from ConflictMap.
 */

import type { GeointAnomaly, SigintAircraft, SigintShip } from "@/types/theaterMap";

export const GEO_URL = "https://unpkg.com/world-atlas@2.0.2/countries-110m.json";

export const CONFLICT_CENTERS: Record<
  string,
  { center: [number, number]; zoom: number }
> = {
  iran: { center: [53, 32], zoom: 4 },
  "us-iran": { center: [53, 28], zoom: 3.5 },
  "middle-east": { center: [44, 31], zoom: 3.5 }, // Levante/Golf/Iran
  hezbollah: { center: [35.8, 33.9], zoom: 5.5 }, // Lebanon
  houthis: { center: [46, 15], zoom: 4 }, // Yemen / Red Sea
  "red-sea": { center: [43, 12], zoom: 4.4 }, // Bab el-Mandeb / Gulf of Aden / Horn
  "red-sea-horn": { center: [43, 12], zoom: 4.4 }, // Bab el-Mandeb / Gulf of Aden / Horn
  "horn-africa": { center: [43, 12], zoom: 4.4 },
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

/** Event types drawn as “strike” markers with halo (ISW-style attack emphasis). */
export const THEATER_STRIKE_LIKE_TYPES = new Set([
  "airstrike",
  "missile",
  "drone",
  "explosion",
  "naval",
]);

export type StrikeAttribution = "us" | "israel" | "axis" | "unknown";

/**
 * Coarse attribution from ACLED/FIRMS text + country (OSINT-style heuristics, not verified truth).
 * Similar idea to strike maps that distinguish coalition vs regional actors.
 */
export function inferStrikeAttribution(evt: {
  label?: string;
  notes?: string;
  actor1?: string;
  actor2?: string;
  sub_event_type?: string;
  country?: string;
}): StrikeAttribution {
  const text = [evt.label, evt.notes, evt.actor1, evt.actor2, evt.sub_event_type]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  if (/\b(us forces|united states|u\.s\. military|usaf|us navy|centcom|american forces|operation inherent)\b/.test(text)) {
    return "us";
  }
  if (/\b(israel|idf|iaf|israel defense|israeli air)\b/.test(text)) {
    return "israel";
  }
  if (
    /\b(iran|irgc|irgc-qf|basij|quds force|houthi|ansarallah|hezbollah|hashd|pmf|pasdaran)\b/.test(text)
  ) {
    return "axis";
  }
  const cy = (evt.country || "").toLowerCase();
  if (cy === "israel") return "israel";
  if (cy === "iran" || cy === "yemen") return "axis";
  return "unknown";
}

/** Fill/stroke for attribution when inferrable; unknown falls back to THEATER_EVENT_STYLE by event_type. */
export const STRIKE_ATTRIBUTION_STYLE: Record<
  StrikeAttribution,
  { label: string; fill: string; stroke: string }
> = {
  us: { label: "US / coalition", fill: "#1d4ed8", stroke: "#1e3a8a" },
  israel: { label: "Israel", fill: "#38bdf8", stroke: "#0284c7" },
  axis: { label: "Iran / axis", fill: "#ea580c", stroke: "#9a3412" },
  unknown: { label: "Unattributed", fill: "#6b7280", stroke: "#4b5563" },
};

type Rgba = [number, number, number, number];

function hexToRgbTuple(hex: string): [number, number, number] {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return [107, 114, 128];
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Deck.gl colors: attribution when inferrable, else event_type palette. */
export function strikeMarkerColors(evt: {
  event_type: string;
  label?: string;
  notes?: string;
  actor1?: string;
  actor2?: string;
  sub_event_type?: string;
  country?: string;
}): { fill: Rgba; stroke: Rgba; halo: Rgba } {
  const attr = inferStrikeAttribution(evt);
  if (attr === "unknown") {
    const style = THEATER_EVENT_STYLE[evt.event_type] ?? THEATER_EVENT_STYLE.other;
    const [r, g, b] = hexToRgbTuple(style.fill);
    const [sr, sg, sb] = hexToRgbTuple(style.stroke);
    return {
      fill: [r, g, b, 230],
      stroke: [sr, sg, sb, 255],
      halo: [r, g, b, 72],
    };
  }
  const style = STRIKE_ATTRIBUTION_STYLE[attr];
  const [r, g, b] = hexToRgbTuple(style.fill);
  const [sr, sg, sb] = hexToRgbTuple(style.stroke);
  return {
    fill: [r, g, b, 238],
    stroke: [sr, sg, sb, 255],
    halo: [r, g, b, 85],
  };
}

/**
 * Conflict keys for which SAM / Air routes / Sea lanes overlay data exists (Iran/Gulf/Levant).
 * For other conflicts, those overlays are not rendered.
 */
export const OVERLAY_CONFLICT_KEYS = [
  "iran",
  "us-iran",
  "middle-east",
  "hezbollah",
  "houthis",
  "israel-palestine",
  "lebanon",
  "yemen",
  "red-sea",
  "red-sea-horn",
  "horn-africa",
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

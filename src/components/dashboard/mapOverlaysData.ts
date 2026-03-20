/**
 * Static overlay data for ConflictMap: SAM rings, air routes, sea lanes.
 * Coordinates are [longitude, latitude] (GeoJSON order). Replace with your own GeoJSON or OSINT data.
 */

export interface SamRing {
  id: string;
  name: string;
  /** Center [lon, lat] */
  center: [number, number];
  /** Radius in km (approximate engagement zone) */
  radius_km: number;
}

export interface MapPolyline {
  id: string;
  name: string;
  /** [lon, lat] ordered points */
  coordinates: [number, number][];
}

export interface StrategicSite {
  id: string;
  name: string;
  country: string;
  /** Center [lon, lat] */
  coordinates: [number, number];
}

/** SAM positions (illustrative; replace with OSINT/vordefinierte Daten). Iran/Gulf region. */
export const SAM_RINGS: SamRing[] = [
  { id: "sam-tehran", name: "Tehran area", center: [51.4, 35.7], radius_km: 150 },
  { id: "sam-bushehr", name: "Bushehr / Gulf", center: [50.8, 28.9], radius_km: 120 },
  { id: "sam-isfahan", name: "Isfahan / central", center: [51.7, 32.6], radius_km: 140 },
  { id: "sam-tabriz", name: "NW Iran", center: [46.3, 38.1], radius_km: 100 },
];

/** Main air corridors (simplified). [lon, lat] segments. */
export const AIR_ROUTES: MapPolyline[] = [
  {
    id: "air-gulf-corridor",
    name: "Gulf corridor",
    coordinates: [
      [47.5, 29.3],
      [50.0, 26.2],
      [51.5, 25.3],
      [54.0, 24.5],
    ],
  },
  {
    id: "air-levant-gulf",
    name: "Levant–Gulf",
    coordinates: [
      [35.5, 33.5],
      [38.0, 34.0],
      [42.0, 32.0],
      [48.0, 28.0],
      [51.0, 26.0],
    ],
  },
  {
    id: "air-redsea",
    name: "Red Sea / Sinai",
    coordinates: [
      [32.4, 29.8],
      [34.3, 28.5],
      [38.5, 22.0],
      [43.0, 15.0],
    ],
  },
];

/** Sea lanes (simplified). Strait of Hormuz, Bab el Mandeb, Suez approach. */
export const SEA_LANES: MapPolyline[] = [
  {
    id: "sea-hormuz",
    name: "Strait of Hormuz",
    coordinates: [
      [56.0, 26.5],
      [57.0, 26.2],
      [58.2, 26.0],
      [59.0, 25.5],
    ],
  },
  {
    id: "sea-bab-el-mandeb",
    name: "Bab el Mandeb",
    coordinates: [
      [43.2, 12.6],
      [43.4, 12.5],
      [43.5, 12.4],
    ],
  },
  {
    id: "sea-suez-approach",
    name: "Suez / Gulf of Suez",
    coordinates: [
      [32.3, 29.9],
      [33.0, 28.5],
      [33.5, 27.8],
    ],
  },
];

export interface ChokePointZone {
  id: string;
  name: string;
  /** [lon, lat] vertices forming a closed polygon */
  vertices: [number, number][];
}

/**
 * Chokepoint zone polygons for overlay rendering.
 * Coordinates in [lon, lat] (GeoJSON order). Polygons match backend compliance/zones.py.
 */
export const CHOKEPOINT_ZONES: ChokePointZone[] = [
  {
    id: "zone-hormuz",
    name: "Strait of Hormuz",
    vertices: [
      [55.5, 26.0], [55.0, 27.2], [56.5, 27.0],
      [57.5, 26.5], [57.0, 25.8], [56.0, 25.5],
      [55.5, 26.0],
    ],
  },
  {
    id: "zone-bab-el-mandeb",
    name: "Bab el-Mandeb",
    vertices: [
      [43.0, 12.4], [43.0, 12.8], [43.6, 12.8],
      [43.6, 12.4], [43.0, 12.4],
    ],
  },
  {
    id: "zone-suez",
    name: "Suez Canal",
    vertices: [
      [32.2, 29.8], [32.2, 31.3], [32.6, 31.3],
      [32.6, 29.8], [32.2, 29.8],
    ],
  },
];

/** Major military bases (illustrative strategic overlay for TheaterMap). */
export const MILITARY_BASES: StrategicSite[] = [
  { id: "mb-al-udeid", name: "Al Udeid Air Base", country: "Qatar", coordinates: [51.313, 25.117] },
  { id: "mb-al-dhafra", name: "Al Dhafra Air Base", country: "UAE", coordinates: [54.548, 24.248] },
  { id: "mb-incirlik", name: "Incirlik Air Base", country: "Turkey", coordinates: [35.425, 37.002] },
  { id: "mb-bah-rss", name: "NSA Bahrain", country: "Bahrain", coordinates: [50.606, 26.191] },
  { id: "mb-camp-arifjan", name: "Camp Arifjan", country: "Kuwait", coordinates: [47.906, 28.848] },
  { id: "mb-al-asad", name: "Al Asad Air Base", country: "Iraq", coordinates: [41.031, 33.785] },
  { id: "mb-diego-garcia", name: "Diego Garcia", country: "BIOT", coordinates: [72.411, -7.313] },
];

/** Civilian and strategic nuclear facilities (illustrative strategic overlay). */
export const NUCLEAR_FACILITIES: StrategicSite[] = [
  { id: "nf-bushehr", name: "Bushehr Nuclear Plant", country: "Iran", coordinates: [50.887, 28.829] },
  { id: "nf-natanz", name: "Natanz Fuel Enrichment Plant", country: "Iran", coordinates: [51.726, 33.725] },
  { id: "nf-fordow", name: "Fordow Fuel Enrichment Plant", country: "Iran", coordinates: [50.992, 34.885] },
  { id: "nf-isfahan", name: "Isfahan Nuclear Technology Center", country: "Iran", coordinates: [51.654, 32.648] },
  { id: "nf-dimona", name: "Dimona Nuclear Research Center", country: "Israel", coordinates: [35.145, 31.001] },
  { id: "nf-akkuyu", name: "Akkuyu Nuclear Power Plant", country: "Turkey", coordinates: [33.496, 36.146] },
  { id: "nf-barakah", name: "Barakah Nuclear Power Plant", country: "UAE", coordinates: [52.322, 24.141] },
];

/** Generate polygon points for a circle (WGS84 approx). Returns [lon, lat][] closed ring. */
export function circlePoints(centerLon: number, centerLat: number, radiusKm: number, steps = 64): [number, number][] {
  const points: [number, number][] = [];
  const latDegPerKm = 1 / 111.32;
  const lonDegPerKm = 1 / (111.32 * Math.cos((centerLat * Math.PI) / 180));
  for (let i = 0; i <= steps; i++) {
    const angle = (2 * Math.PI * i) / steps;
    const lon = centerLon + (radiusKm * lonDegPerKm) * Math.cos(angle);
    const lat = centerLat + (radiusKm * latDegPerKm) * Math.sin(angle);
    points.push([lon, lat]);
  }
  return points;
}

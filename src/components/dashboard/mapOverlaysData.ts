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

export interface MapPoint {
  id: string;
  name: string;
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
    name: "Bab-el-Mandeb",
    vertices: [
      [43.0, 12.4], [43.0, 12.8], [43.6, 12.8],
      [43.6, 12.4], [43.0, 12.4],
    ],
  },
  {
    id: "zone-suez",
    name: "Suez",
    vertices: [
      [32.2, 29.8], [32.2, 31.3], [32.6, 31.3],
      [32.6, 29.8], [32.2, 29.8],
    ],
  },
];

/** Major military bases (illustrative strategic overlay for TheaterMap). */
export const MILITARY_BASES: StrategicSite[] = [
  { id: "mb-us-al-udeid", name: "US Air Base – Al Udeid", country: "Qatar", coordinates: [51.313, 25.117] },
  { id: "mb-us-al-dhafra", name: "US Air Base – Al Dhafra", country: "UAE", coordinates: [54.548, 24.248] },
  { id: "mb-us-nsa-bahrain", name: "US Naval Support Activity – Bahrain", country: "Bahrain", coordinates: [50.606, 26.191] },
  { id: "mb-us-diego-garcia", name: "US Support Facility – Diego Garcia", country: "BIOT", coordinates: [72.411, -7.313] },
  { id: "mb-us-camp-lemonnier", name: "US Base – Camp Lemonnier", country: "Djibouti", coordinates: [43.148, 11.547] },
  { id: "mb-us-ain-al-asad", name: "US Air Base – Ain al-Asad", country: "Iraq", coordinates: [41.031, 33.785] },
  { id: "mb-idf-nevatim", name: "IDF Base – Nevatim (F-35I)", country: "Israel", coordinates: [35.012, 31.208] },
  { id: "mb-idf-hatzerim", name: "IDF Base – Hatzerim (F-16I)", country: "Israel", coordinates: [34.723, 31.233] },
  { id: "mb-idf-ramat-david", name: "IDF Base – Ramat David (F-15I)", country: "Israel", coordinates: [35.179, 32.665] },
  { id: "mb-idf-palmachim", name: "IDF Base – Palmachim (Arrow/Jericho)", country: "Israel", coordinates: [34.692, 31.931] },
];

/** Civilian and strategic nuclear facilities (illustrative strategic overlay). */
export const NUCLEAR_FACILITIES: StrategicSite[] = [
  { id: "nf-natanz", name: "Natanz (DAMAGED)", country: "Iran", coordinates: [51.726, 33.725] },
  { id: "nf-fordow", name: "Fordow (DAMAGED)", country: "Iran", coordinates: [50.992, 34.885] },
  { id: "nf-isfahan", name: "Isfahan", country: "Iran", coordinates: [51.654, 32.648] },
  { id: "nf-bushehr", name: "Bushehr", country: "Iran", coordinates: [50.887, 28.829] },
];

/** UN Blue Line (approximate polyline segments for South Lebanon monitoring). */
export const BLUE_LINE_PATHS: MapPolyline[] = [
  {
    id: "blue-line-west-east",
    name: "UN Blue Line",
    coordinates: [
      [35.095, 33.105],
      [35.15, 33.13],
      [35.23, 33.16],
      [35.31, 33.18],
      [35.42, 33.17],
      [35.53, 33.21],
      [35.62, 33.24],
      [35.73, 33.26],
      [35.84, 33.28],
      [35.98, 33.30],
      [36.12, 33.31],
      [36.26, 33.31],
    ],
  },
];

/** UNIFIL post markers (illustrative, replace with validated geodata in production). */
export const UNIFIL_POSTS: MapPoint[] = [
  { id: "unifil-naqoura", name: "UNIFIL HQ Naqoura", coordinates: [35.114, 33.119] },
  { id: "unifil-bint-jbeil", name: "UNIFIL Bint Jbeil Sector", coordinates: [35.428, 33.119] },
  { id: "unifil-marjayoun", name: "UNIFIL Marjayoun Sector", coordinates: [35.593, 33.363] },
  { id: "unifil-khiam", name: "UNIFIL Khiam Vicinity", coordinates: [35.632, 33.346] },
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

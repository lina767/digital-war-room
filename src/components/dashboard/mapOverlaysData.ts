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

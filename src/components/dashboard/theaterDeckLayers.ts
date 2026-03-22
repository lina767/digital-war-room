import { PathLayer, PolygonLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { PathStyleExtension } from "@deck.gl/extensions";
import type { Layer } from "@deck.gl/core";
import type { ConflictEventForHeatmap, TheaterEvent } from "@/lib/api";
import {
  THEATER_EVENT_STYLE,
  type GeointAnomaly,
  type SigintAircraft,
  type SigintShip,
  hasOverlayDataForConflict,
} from "./mapConfig";
import {
  AIR_ROUTES,
  CHOKEPOINT_ZONES,
  MILITARY_BASES,
  NUCLEAR_FACILITIES,
  SEA_LANES,
  type ChokePointZone,
} from "./mapOverlaysData";
import type { TheaterDisplayItem } from "./theaterMapCluster";

/** Matches dashboard chokepoint payload; duplicated here to avoid circular imports. */
export interface ChokepointStatusInput {
  name: string;
  status: "OPEN" | "RESTRICTED" | "DISRUPTED" | "HOSTILE";
  disruption_risk: number;
}

const DEFAULT_CHOKEPOINT_STATUSES: ChokepointStatusInput[] = [
  { name: "Strait of Hormuz", status: "RESTRICTED", disruption_risk: 65 },
  { name: "Bab-el-Mandeb", status: "HOSTILE", disruption_risk: 85 },
  { name: "Suez", status: "OPEN", disruption_risk: 20 },
];

function normalizeChokepointName(name: string): string {
  const normalized = name.toLowerCase().replace(/[\s-]+/g, "").replace(/[^a-z]/g, "");
  if (normalized.includes("hormuz")) return "hormuz";
  if (normalized.includes("babelmandeb")) return "babelmandeb";
  if (normalized.includes("suez")) return "suez";
  return normalized;
}

function hexToRgba(hex: string, a = 255): [number, number, number, number] {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return [128, 128, 128, a];
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255, a];
}

/** Logarithmic marker scale — visually consistent across zoom 2..8 */
export function markerScale(zoom: number): number {
  return Math.max(0.15, 1 / Math.sqrt(zoom));
}

const GEOINT_ORANGE: [number, number, number, number] = [255, 68, 0, 255];
const SIGINT_AIR: [number, number, number, number] = [96, 165, 250, 255];
const SIGINT_SEA: [number, number, number, number] = [52, 211, 153, 255];
export type TheaterPick =
  | { kind: "theater"; event: TheaterEvent }
  | { kind: "aircraft"; data: SigintAircraft }
  | { kind: "ship"; data: SigintShip };

export interface TheaterDeckLayersInput {
  zoom: number;
  activeConflict: string | null;
  layerVisibility: {
    theaterEvents: boolean;
    geoint: boolean;
    sigint: boolean;
    heatmap: boolean;
    samRings: boolean;
    airRoutes: boolean;
    seaLanes: boolean;
    chokepoints: boolean;
    militaryBases: boolean;
    nuclearFacilities: boolean;
  };
  samRingLines: Array<{ id: string; coords: [number, number][] }>;
  theaterDisplayItems: TheaterDisplayItem[];
  heatmapEvents: ConflictEventForHeatmap[];
  geointAnomalies: GeointAnomaly[];
  sigintAircraft: SigintAircraft[];
  sigintShips: SigintShip[];
  chokepointStatuses: ChokepointStatusInput[];
}

function chokepointZoneData(
  zones: ChokePointZone[],
  statuses: ChokepointStatusInput[],
): Array<{
  id: string;
  polygon: [number, number][];
  fill: [number, number, number, number];
  line: [number, number, number, number];
  tooltip: string;
}> {
  return zones.map((zone) => {
    const zoneKey = normalizeChokepointName(zone.name);
    const match =
      statuses.find((cp) => normalizeChokepointName(cp.name) === zoneKey) ??
      DEFAULT_CHOKEPOINT_STATUSES.find((cp) => normalizeChokepointName(cp.name) === zoneKey);
    const riskFromStatus =
      match?.status === "HOSTILE"
        ? 90
        : match?.status === "DISRUPTED"
          ? 80
          : match?.status === "RESTRICTED"
            ? 60
            : 20;
    const risk = Math.max(match?.disruption_risk ?? 0, riskFromStatus);
    const fill: [number, number, number, number] =
      risk >= 70
        ? [220, 38, 38, 45]
        : risk >= 40
          ? [234, 179, 8, 40]
          : [16, 185, 129, 30];
    const line: [number, number, number, number] =
      risk >= 70
        ? [220, 38, 38, 130]
        : risk >= 40
          ? [234, 179, 8, 110]
          : [16, 185, 129, 90];
    const tooltipContent = match
      ? `${zone.name} · ${match.status} · Risk ${match.disruption_risk}%`
      : zone.name;
    return {
      id: zone.id,
      polygon: zone.vertices,
      fill,
      line,
      tooltip: tooltipContent,
    };
  });
}

const pathDashExt = new PathStyleExtension({ dash: true });

/**
 * Builds deck.gl layers for the theater map (WebGL). Order: lines → polygons → heatmap → points (top = last).
 */
export function buildTheaterDeckLayers(input: TheaterDeckLayersInput): Layer[] {
  const {
    zoom,
    activeConflict,
    layerVisibility: lv,
    samRingLines,
    theaterDisplayItems,
    heatmapEvents,
    geointAnomalies,
    sigintAircraft,
    sigintShips,
    chokepointStatuses,
  } = input;

  const s = markerScale(zoom);
  const overlayOk = hasOverlayDataForConflict(activeConflict);
  const layers: Layer[] = [];

  if (lv.samRings && overlayOk && samRingLines.length > 0) {
    layers.push(
      new PathLayer({
        id: "sam-rings",
        data: samRingLines,
        getPath: (d) => d.coords,
        getColor: [220, 38, 38, 150],
        getWidth: 1.5,
        widthUnits: "pixels",
        capRounded: true,
        jointRounded: true,
        extensions: [pathDashExt],
        getDashArray: [2, 2],
        pickable: false,
      }),
    );
  }

  if (lv.airRoutes && overlayOk) {
    layers.push(
      new PathLayer({
        id: "air-routes",
        data: AIR_ROUTES,
        getPath: (d) => d.coordinates,
        getColor: [56, 189, 248, 210],
        getWidth: 2,
        widthUnits: "pixels",
        capRounded: true,
        extensions: [pathDashExt],
        getDashArray: [4, 2],
        pickable: false,
      }),
    );
  }

  if (lv.seaLanes && overlayOk) {
    layers.push(
      new PathLayer({
        id: "sea-lanes",
        data: SEA_LANES,
        getPath: (d) => d.coordinates,
        getColor: [45, 212, 191, 210],
        getWidth: 1.8,
        widthUnits: "pixels",
        capRounded: true,
        extensions: [pathDashExt],
        getDashArray: [3, 2],
        pickable: false,
      }),
    );
  }

  if (lv.chokepoints) {
    const cpData = chokepointZoneData(CHOKEPOINT_ZONES, chokepointStatuses);
    layers.push(
      new PolygonLayer({
        id: "chokepoints",
        data: cpData,
        getPolygon: (d) => d.polygon,
        filled: true,
        stroked: true,
        getFillColor: (d) => d.fill,
        getLineColor: (d) => d.line,
        getLineWidth: 1,
        lineWidthUnits: "pixels",
        pickable: true,
      }),
    );
  }

  if (lv.heatmap && heatmapEvents.length > 0) {
    const validHeat = heatmapEvents.filter(
      (e) => typeof e.lat === "number" && typeof e.lon === "number" && isFinite(e.lat) && isFinite(e.lon),
    );
    if (validHeat.length > 0) {
      layers.push(
        new HeatmapLayer({
          id: "acled-heatmap",
          data: validHeat,
          getPosition: (d) => [d.lon, d.lat],
          getWeight: (d) => 0.2 + (d.intensity ?? 0) * 2,
          radiusPixels: 28 + s * 8,
          intensity: 1,
          threshold: 0.05,
          aggregation: "SUM",
          colorRange: [
            [255, 255, 178, 0],
            [254, 217, 118, 120],
            [254, 178, 76, 180],
            [253, 141, 60, 220],
            [252, 78, 42, 240],
            [227, 26, 28, 255],
          ],
          pickable: false,
        }),
      );
    }
  }

  if (lv.militaryBases && overlayOk) {
    layers.push(
      new ScatterplotLayer({
        id: "bases-military",
        data: MILITARY_BASES.map((b) => ({
          ...b,
          tooltip: `${b.name} · ${b.country}`,
        })),
        getPosition: (d) => [...d.coordinates] as [number, number],
        getRadius: 5 * s,
        radiusUnits: "pixels",
        getFillColor: [96, 165, 250, 200],
        getLineColor: [59, 130, 246, 255],
        lineWidthUnits: "pixels",
        getLineWidth: 1,
        stroked: true,
        pickable: true,
        radiusMinPixels: 4,
        radiusMaxPixels: 28,
      }),
    );
  }

  if (lv.nuclearFacilities && overlayOk) {
    layers.push(
      new ScatterplotLayer({
        id: "bases-nuclear",
        data: NUCLEAR_FACILITIES.map((b) => ({
          ...b,
          tooltip: `${b.name} · ${b.country}`,
        })),
        getPosition: (d) => [...d.coordinates] as [number, number],
        getRadius: 5 * s,
        radiusUnits: "pixels",
        getFillColor: [234, 179, 8, 210],
        getLineColor: [202, 138, 4, 255],
        lineWidthUnits: "pixels",
        getLineWidth: 1,
        stroked: true,
        pickable: true,
        radiusMinPixels: 4,
        radiusMaxPixels: 28,
      }),
    );
  }

  const theaterEvents = theaterDisplayItems.filter((i) => i.type === "event");

  if (lv.theaterEvents && theaterEvents.length > 0) {
    layers.push(
      new ScatterplotLayer({
        id: "theater-events",
        data: theaterEvents.map((item) => {
          const evt = item.event;
          const style = THEATER_EVENT_STYLE[evt.event_type] ?? THEATER_EVENT_STYLE.other;
          const [r, g, b] = hexToRgba(style.fill, 255);
          return {
            position: [evt.lon, evt.lat] as [number, number],
            pick: { kind: "theater" as const, event: evt },
            fill: [r, g, b, 230] as [number, number, number, number],
            stroke: [...hexToRgba(style.stroke, 255).slice(0, 3), 255] as [number, number, number, number],
          };
        }),
        getPosition: (d) => d.position,
        getRadius: 7 * s,
        radiusUnits: "pixels",
        getFillColor: (d) => d.fill,
        getLineColor: (d) => d.stroke,
        lineWidthUnits: "pixels",
        getLineWidth: 1.2,
        stroked: true,
        pickable: true,
        radiusMinPixels: 5,
        radiusMaxPixels: 32,
      }),
    );
  }

  if (lv.geoint) {
    const valid = geointAnomalies.filter(
      (a) =>
        typeof a.latitude === "number" &&
        typeof a.longitude === "number" &&
        isFinite(a.latitude) &&
        isFinite(a.longitude),
    );
    if (valid.length > 0) {
      layers.push(
        new ScatterplotLayer({
          id: "geoint-anomalies",
          data: valid.map((a) => ({
            position: [a.longitude, a.latitude] as [number, number],
            r: Math.min(3 + (a.frp ?? 0) / 200, 8) * s,
            tooltip: `${a.classification ?? "unknown"} · FRP ${Math.round(a.frp ?? 0)} MW`,
          })),
          getPosition: (d) => d.position,
          getRadius: (d) => d.r,
          radiusUnits: "pixels",
          getFillColor: [...GEOINT_ORANGE.slice(0, 3), 210] as [number, number, number, number],
          getLineColor: [255, 34, 0, 255],
          lineWidthUnits: "pixels",
          getLineWidth: 1,
          stroked: true,
          pickable: true,
          radiusMinPixels: 4,
          radiusMaxPixels: 40,
        }),
      );
    }
  }

  if (lv.sigint) {
    const ac = sigintAircraft.filter(
      (a) => typeof a.lat === "number" && typeof a.lon === "number" && isFinite(a.lat) && isFinite(a.lon),
    );
    if (ac.length > 0) {
      layers.push(
        new ScatterplotLayer({
          id: "sigint-air",
          data: ac.map((a) => ({
            position: [a.lon, a.lat] as [number, number],
            pick: { kind: "aircraft" as const, data: a },
          })),
          getPosition: (d) => d.position,
          getRadius: 6 * s,
          radiusUnits: "pixels",
          getFillColor: [...SIGINT_AIR.slice(0, 3), 230] as [number, number, number, number],
          getLineColor: [37, 99, 235, 255],
          lineWidthUnits: "pixels",
          getLineWidth: 1,
          stroked: true,
          pickable: true,
        }),
      );
    }

    const ships = sigintShips.filter(
      (sh) => typeof sh.lat === "number" && typeof sh.lon === "number" && isFinite(sh.lat) && isFinite(sh.lon),
    );
    if (ships.length > 0) {
      layers.push(
        new ScatterplotLayer({
          id: "sigint-sea",
          data: ships.map((sh) => ({
            position: [sh.lon, sh.lat] as [number, number],
            pick: { kind: "ship" as const, data: sh },
          })),
          getPosition: (d) => d.position,
          getRadius: 6 * s,
          radiusUnits: "pixels",
          getFillColor: [...SIGINT_SEA.slice(0, 3), 230] as [number, number, number, number],
          getLineColor: [5, 150, 105, 255],
          lineWidthUnits: "pixels",
          getLineWidth: 1,
          stroked: true,
          pickable: true,
        }),
      );
    }
  }

  if (overlayOk && zoom >= 4) {
    const labelData: Array<{ pos: [number, number]; text: string; color: [number, number, number, number] }> = [];
    if (lv.airRoutes) {
      for (const route of AIR_ROUTES) {
        const mid = route.coordinates[Math.floor(route.coordinates.length / 2)];
        labelData.push({
          pos: [mid[0], mid[1]],
          text: route.name,
          color: [56, 189, 248, 230],
        });
      }
    }
    if (lv.seaLanes) {
      for (const lane of SEA_LANES) {
        const mid = lane.coordinates[Math.floor(lane.coordinates.length / 2)];
        labelData.push({
          pos: [mid[0], mid[1]],
          text: lane.name,
          color: [45, 212, 191, 230],
        });
      }
    }
    if (labelData.length > 0) {
      layers.push(
        new TextLayer({
          id: "route-labels",
          data: labelData,
          getPosition: (d) => d.pos,
          getText: (d) => d.text,
          getSize: 11,
          getColor: (d) => d.color,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontWeight: 500,
          outlineWidth: 2,
          outlineColor: [10, 10, 12, 200],
          pickable: false,
          billboard: true,
        }),
      );
    }
  }

  return layers;
}

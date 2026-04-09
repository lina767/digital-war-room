import { PathLayer, PolygonLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { PathStyleExtension } from "@deck.gl/extensions";
import type { Layer } from "@deck.gl/core";
import type { ConflictEventForHeatmap, TheaterEvent } from "@/lib/api";
import {
  THEATER_STRIKE_LIKE_TYPES,
  strikeMarkerColors,
  hasOverlayDataForConflict,
} from "./mapConfig";
import type { GeointAnomaly, SigintAircraft, SigintShip } from "@/types/theaterMap";
import {
  AIR_ROUTES,
  BLUE_LINE_PATHS,
  CHOKEPOINT_ZONES,
  MILITARY_BASES,
  NUCLEAR_FACILITIES,
  SEA_LANES,
  UNIFIL_POSTS,
  type ChokePointZone,
} from "./mapOverlaysData";
import type { TheaterDisplayItem } from "./theaterMapCluster";
import type { LayerVisibility } from "@/features/theater-map/config/layerVisibility";

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

/** Logarithmic marker scale – visually consistent across zoom 2..8 */
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
  layerVisibility: LayerVisibility;
  samRingLines: Array<{ id: string; coords: [number, number][] }>;
  theaterDisplayItems: TheaterDisplayItem[];
  heatmapEvents: ConflictEventForHeatmap[];
  geointAnomalies: GeointAnomaly[];
  sigintAircraft: SigintAircraft[];
  sigintShips: SigintShip[];
  chokepointStatuses: ChokepointStatusInput[];
  villageImpactPoints?: Array<{
    name: string;
    lat: number;
    lon: number;
    score: number;
    correlation: number;
    launches: number;
    responses: number;
  }>;
  idpSignals?: Array<{
    name: string;
    lat: number;
    lon: number;
    intensity: number;
    description?: string;
  }>;
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
  const statusByKey = new Map<string, ChokepointStatusInput>();
  for (const cp of statuses) statusByKey.set(normalizeChokepointName(cp.name), cp);
  const defaultByKey = new Map<string, ChokepointStatusInput>();
  for (const cp of DEFAULT_CHOKEPOINT_STATUSES) defaultByKey.set(normalizeChokepointName(cp.name), cp);

  return zones.map((zone) => {
    const zoneKey = normalizeChokepointName(zone.name);
    const match = statusByKey.get(zoneKey) ?? defaultByKey.get(zoneKey);
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

function sanitizeLabelText(text: string): string {
  return text.replace(/[––]/g, "-");
}

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
    villageImpactPoints = [],
    idpSignals = [],
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

  if (lv.blueLine && overlayOk) {
    layers.push(
      new PathLayer({
        id: "blue-line",
        data: BLUE_LINE_PATHS,
        getPath: (d) => d.coordinates,
        getColor: [96, 165, 250, 220],
        getWidth: 2.2,
        widthUnits: "pixels",
        capRounded: true,
        jointRounded: true,
        extensions: [pathDashExt],
        getDashArray: [6, 3],
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
    layers.push(
      new HeatmapLayer({
        id: "acled-heatmap",
        data: heatmapEvents,
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
        /** Face camera — default false makes flat circles smear into ellipses when the map is pitched. */
        billboard: true,
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
        billboard: true,
      }),
    );
  }

  if (lv.unifilPosts && overlayOk) {
    layers.push(
      new ScatterplotLayer({
        id: "unifil-posts",
        data: UNIFIL_POSTS.map((p) => ({ ...p, tooltip: `${p.name} · UNIFIL post` })),
        getPosition: (d) => [...d.coordinates] as [number, number],
        getRadius: 6 * s,
        radiusUnits: "pixels",
        getFillColor: [147, 197, 253, 220],
        getLineColor: [37, 99, 235, 255],
        lineWidthUnits: "pixels",
        getLineWidth: 1.1,
        stroked: true,
        pickable: true,
        radiusMinPixels: 5,
        radiusMaxPixels: 26,
        billboard: true,
      }),
    );
  }

  const theaterEvents = theaterDisplayItems.filter((i) => i.type === "event");

  if (lv.theaterEvents && theaterEvents.length > 0) {
    const strikeHalos = theaterEvents
      .map((item) => item.event)
      .filter((evt) => THEATER_STRIKE_LIKE_TYPES.has(evt.event_type));
    if (strikeHalos.length > 0) {
      layers.push(
        new ScatterplotLayer({
          id: "theater-strike-halos",
          data: strikeHalos.map((evt) => {
            const { halo } = strikeMarkerColors(evt);
            return {
              position: [evt.lon, evt.lat] as [number, number],
              halo,
            };
          }),
          getPosition: (d) => d.position,
          getRadius: 13 * s,
          radiusUnits: "pixels",
          getFillColor: (d) => d.halo,
          stroked: false,
          pickable: false,
          radiusMinPixels: 8,
          radiusMaxPixels: 48,
          billboard: true,
        }),
      );
    }

    layers.push(
      new ScatterplotLayer({
        id: "theater-events",
        data: theaterEvents.map((item) => {
          const evt = item.event;
          const { fill, stroke } = strikeMarkerColors(evt);
          return {
            position: [evt.lon, evt.lat] as [number, number],
            pick: { kind: "theater" as const, event: evt },
            fill,
            stroke,
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
        billboard: true,
      }),
    );
  }

  if (lv.geoint) {
    if (geointAnomalies.length > 0) {
      layers.push(
        new ScatterplotLayer({
          id: "geoint-anomalies",
          data: geointAnomalies.map((a) => ({
            position: [a.longitude, a.latitude] as [number, number],
            r: Math.min(3 + (a.frp ?? 0) / 200, 10) * s,
            tooltip: `${(a.classification || (a as { type?: string }).type) ?? "thermal"} · FRP ${Math.round(a.frp ?? 0)} MW`,
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
          billboard: true,
        }),
      );
    }
  }

  if (lv.villageImpact && villageImpactPoints.length > 0) {
    layers.push(
      new ScatterplotLayer({
        id: "village-impact",
        data: villageImpactPoints.map((d) => ({
          ...d,
          tooltip: `${d.name} · Impact ${Math.round(d.score)} · Corr ${d.correlation.toFixed(2)} · launches ${d.launches} / responses ${d.responses}`,
        })),
        getPosition: (d) => [d.lon, d.lat] as [number, number],
        getRadius: (d) => Math.max(4, Math.min(12, 3 + d.score / 18)) * s,
        radiusUnits: "pixels",
        getFillColor: (d) =>
          d.score >= 75
            ? [220, 38, 38, 220]
            : d.score >= 45
              ? [234, 179, 8, 210]
              : [16, 185, 129, 205],
        getLineColor: [255, 255, 255, 220],
        lineWidthUnits: "pixels",
        getLineWidth: 1,
        stroked: true,
        pickable: true,
        billboard: true,
      }),
    );
  }

  if (lv.idpOverlay && idpSignals.length > 0) {
    layers.push(
      new ScatterplotLayer({
        id: "idp-overlay",
        data: idpSignals.map((d) => ({
          ...d,
          tooltip: `${d.name} · IDP signal ${Math.round(d.intensity)}${d.description ? ` · ${d.description}` : ""}`,
        })),
        getPosition: (d) => [d.lon, d.lat] as [number, number],
        getRadius: (d) => Math.max(4, Math.min(11, 2 + d.intensity / 20)) * s,
        radiusUnits: "pixels",
        getFillColor: [168, 85, 247, 210],
        getLineColor: [126, 34, 206, 255],
        lineWidthUnits: "pixels",
        getLineWidth: 1,
        stroked: true,
        pickable: true,
        billboard: true,
      }),
    );
  }

  if (lv.sigint) {
    if (sigintAircraft.length > 0) {
      layers.push(
        new ScatterplotLayer({
          id: "sigint-air",
          data: sigintAircraft.map((a) => ({
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
          billboard: true,
        }),
      );
    }

    if (sigintShips.length > 0) {
      layers.push(
        new ScatterplotLayer({
          id: "sigint-sea",
          data: sigintShips.map((sh) => ({
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
          billboard: true,
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
          text: sanitizeLabelText(route.name),
          color: [56, 189, 248, 230],
        });
      }
    }
    if (lv.seaLanes) {
      for (const lane of SEA_LANES) {
        const mid = lane.coordinates[Math.floor(lane.coordinates.length / 2)];
        labelData.push({
          pos: [mid[0], mid[1]],
          text: sanitizeLabelText(lane.name),
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
          fontSettings: { sdf: true },
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

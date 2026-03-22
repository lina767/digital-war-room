import { useEffect, useState, useCallback, useMemo, useReducer, memo, useRef } from "react";
import { Plus, Minus, X, AlertTriangle } from "lucide-react";
import { DeckGL } from "@deck.gl/react";
import type { PickingInfo } from "@deck.gl/core";
import MapLibreMap from "react-map-gl/maplibre";
import MapboxMap from "react-map-gl/mapbox";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "mapbox-gl/dist/mapbox-gl.css";
import {
  getConflictEvents,
  getTheaterEvents,
  type ConflictEventForHeatmap,
  type TheaterEvent,
} from "@/lib/api";
import {
  CONFLICT_CENTERS,
  matchConflict,
  THEATER_EVENT_STYLE,
  type GeointAnomaly,
  type SigintAircraft,
  type SigintShip,
} from "./mapConfig";
import { MapLoadingSkeleton } from "@/components/ui/skeleton";
import { SAM_RINGS, circlePoints } from "./mapOverlaysData";
import { buildTheaterDeckLayers, type TheaterPick } from "./theaterDeckLayers";
import { buildTheaterDisplayItems } from "./theaterMapCluster";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface TooltipData {
  content: string;
  color: string;
  x: number;
  y: number;
}

interface LayerVisibility {
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
}

type LayerAction = { type: "TOGGLE"; layer: keyof LayerVisibility };
type ExplosionTimeRange = "6h" | "24h" | "48h" | "7d" | "all";

const INITIAL_LAYERS: LayerVisibility = {
  theaterEvents: true,
  geoint: true,
  sigint: true,
  heatmap: false,
  samRings: false,
  airRoutes: true,
  seaLanes: true,
  chokepoints: true,
  militaryBases: true,
  nuclearFacilities: true,
};

function layerReducer(state: LayerVisibility, action: LayerAction): LayerVisibility {
  return { ...state, [action.layer]: !state[action.layer] };
}

function parseEventTimestamp(value?: string): number | null {
  if (!value) return null;
  const raw = value.trim();
  if (!raw) return null;

  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(raw);
  const normalized = isDateOnly ? `${raw}T00:00:00Z` : raw;
  const parsed = Date.parse(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function withinExplosionRange(evt: TheaterEvent, range: ExplosionTimeRange): boolean {
  if (range === "all" || evt.event_type !== "explosion") return true;

  const hoursByRange: Record<Exclude<ExplosionTimeRange, "all">, number> = {
    "6h": 6,
    "24h": 24,
    "48h": 48,
    "7d": 7 * 24,
  };

  const timestamp = parseEventTimestamp(evt.event_date ?? evt.date_start);
  if (timestamp == null) return false;

  const cutoff = Date.now() - hoursByRange[range] * 60 * 60 * 1000;
  return timestamp >= cutoff;
}

/** Carto vector style — used when `VITE_MAPBOX_TOKEN` is not set (no Mapbox map load). */
const FALLBACK_MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const MAPBOX_DEFAULT_STYLE = "mapbox://styles/mapbox/dark-v11";

const MAPBOX_TOKEN = (() => {
  const raw = import.meta.env.VITE_MAPBOX_TOKEN;
  if (typeof raw !== "string") return undefined;
  const t = raw.trim();
  return t.length > 0 ? t : undefined;
})();

const MAPBOX_STYLE = (() => {
  const raw = import.meta.env.VITE_MAPBOX_STYLE;
  if (typeof raw === "string" && raw.trim().length > 0) return raw.trim();
  return MAPBOX_DEFAULT_STYLE;
})();

const SIGINT_AIR_COLOR = "var(--map-sigint-air)";
const SIGINT_SEA_COLOR = "var(--map-sigint-sea)";

/* ------------------------------------------------------------------ */
/*  Tooltip (HTML)                                                     */
/* ------------------------------------------------------------------ */

function MapTooltip({ tooltip }: { tooltip: TooltipData | null }) {
  if (!tooltip) return null;
  return (
    <div
      className="fixed z-50 pointer-events-none px-2.5 py-1 rounded border bg-card/95 backdrop-blur-sm shadow-lg text-[11px] font-mono text-foreground whitespace-nowrap"
      style={{
        left: tooltip.x + 14,
        top: tooltip.y - 12,
        borderColor: tooltip.color,
      }}
    >
      {tooltip.content}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export interface ChokePointStatus {
  name: string;
  status: "OPEN" | "RESTRICTED" | "DISRUPTED" | "HOSTILE";
  disruption_risk: number;
}

export interface TheaterMapProps {
  activeConflict?: string | null;
  geointAnomalies?: GeointAnomaly[];
  sigintAircraft?: SigintAircraft[];
  sigintShips?: SigintShip[];
  chokepointStatuses?: ChokePointStatus[];
}

function TheaterMapInner({
  activeConflict = null,
  geointAnomalies = [],
  sigintAircraft = [],
  sigintShips = [],
  chokepointStatuses = [],
}: TheaterMapProps) {
  const [layers, dispatchLayers] = useReducer(layerReducer, INITIAL_LAYERS);
  const toggleLayer = useCallback(
    (layer: keyof LayerVisibility) => dispatchLayers({ type: "TOGGLE", layer }),
    [],
  );

  const [selectedEvent, setSelectedEvent] = useState<TheaterEvent | null>(null);
  const [selectedSigint, setSelectedSigint] = useState<
    { type: "aircraft"; data: SigintAircraft } | { type: "ship"; data: SigintShip } | null
  >(null);
  const [explosionRange, setExplosionRange] = useState<ExplosionTimeRange>("7d");
  const eventClustering = true;
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  const mapContainerRef = useRef<HTMLDivElement>(null);

  const [viewState, setViewState] = useState({
    longitude: 54.0836,
    latitude: 31.7419,
    zoom: 4.73,
    pitch: 0,
    bearing: 0,
  });

  const [theaterEvents, setTheaterEvents] = useState<TheaterEvent[]>([]);
  const [theaterLoading, setTheaterLoading] = useState(false);
  const [theaterError, setTheaterError] = useState<string | null>(null);

  const [heatmapEvents, setHeatmapEvents] = useState<ConflictEventForHeatmap[]>([]);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [heatmapError, setHeatmapError] = useState<string | null>(null);

  const zoom = viewState.zoom;
  const s = markerScale(zoom);

  const tooltipTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const TOOLTIP_DELAY_MS = 180;

  const setTooltipFromDeck = useCallback(
    (content: string, color: string, info: PickingInfo) => {
      const rect = mapContainerRef.current?.getBoundingClientRect();
      const x = (rect?.left ?? 0) + info.x;
      const y = (rect?.top ?? 0) + info.y;
      if (tooltipTimeoutRef.current) {
        clearTimeout(tooltipTimeoutRef.current);
        tooltipTimeoutRef.current = null;
      }
      tooltipTimeoutRef.current = setTimeout(() => {
        tooltipTimeoutRef.current = null;
        setTooltip({ content, color, x, y });
      }, TOOLTIP_DELAY_MS);
    },
    [],
  );

  const handleTooltipHide = useCallback(() => {
    if (tooltipTimeoutRef.current) {
      clearTimeout(tooltipTimeoutRef.current);
      tooltipTimeoutRef.current = null;
    }
    setTooltip(null);
  }, []);

  const handleEventSelect = useCallback((evt: TheaterEvent) => {
    setSelectedEvent(evt);
    setSelectedSigint(null);
    setTooltip(null);
  }, []);

  const handleAircraftSelect = useCallback((ac: SigintAircraft) => {
    setSelectedSigint({ type: "aircraft", data: ac });
    setSelectedEvent(null);
    setTooltip(null);
  }, []);

  const handleShipSelect = useCallback((ship: SigintShip) => {
    setSelectedSigint({ type: "ship", data: ship });
    setSelectedEvent(null);
    setTooltip(null);
  }, []);

  const handleClusterZoomIn = useCallback((lat: number, lon: number) => {
    setViewState((vs) => ({
      ...vs,
      longitude: lon,
      latitude: lat,
      zoom: Math.min(vs.zoom * 1.4, 8),
    }));
    setSelectedEvent(null);
    setTooltip(null);
  }, []);

  const onViewStateChange = useCallback(
    ({ viewState: vs }: { viewState: typeof viewState }) => {
      const z = Math.min(Math.max(vs.zoom, 2), 8);
      setViewState({ ...vs, zoom: z });
    },
    [],
  );

  useEffect(() => {
    if (!activeConflict) return;
    const key = matchConflict(activeConflict);
    if (key && CONFLICT_CENTERS[key]) {
      const { center: c, zoom: z } = CONFLICT_CENTERS[key];
      setViewState((vs) => ({
        ...vs,
        longitude: c[0],
        latitude: c[1],
        zoom: z,
      }));
    }
  }, [activeConflict]);

  useEffect(() => {
    setExplosionRange("7d");
  }, [activeConflict]);

  useEffect(() => {
    if (!layers.heatmap || !activeConflict) {
      setHeatmapEvents([]);
      setHeatmapError(null);
      return;
    }
    setHeatmapLoading(true);
    setHeatmapError(null);
    getConflictEvents(activeConflict, 200)
      .then((data) => setHeatmapEvents(data?.events ?? []))
      .catch((err) => {
        setHeatmapEvents([]);
        setHeatmapError(err?.message ?? "Failed to load heatmap data");
      })
      .finally(() => setHeatmapLoading(false));
  }, [layers.heatmap, activeConflict]);

  useEffect(() => {
    if (!activeConflict || !layers.theaterEvents) {
      setTheaterEvents([]);
      setSelectedEvent(null);
      setTheaterError(null);
      return;
    }
    setTheaterLoading(true);
    setTheaterError(null);
    getTheaterEvents(activeConflict, 400)
      .then((data) => setTheaterEvents(data?.events ?? []))
      .catch((err) => {
        setTheaterEvents([]);
        setTheaterError(err?.message ?? "Failed to load theater events");
      })
      .finally(() => setTheaterLoading(false));
  }, [activeConflict, layers.theaterEvents]);

  const samRingLines = useMemo(
    () =>
      SAM_RINGS.map((sam) => ({
        ...sam,
        coords: circlePoints(sam.center[0], sam.center[1], sam.radius_km),
      })),
    [],
  );

  const filteredTheaterEvents = useMemo(
    () => theaterEvents.filter((evt) => withinExplosionRange(evt, explosionRange)),
    [theaterEvents, explosionRange],
  );

  const theaterDisplayItems = useMemo(
    () =>
      layers.theaterEvents
        ? buildTheaterDisplayItems(filteredTheaterEvents, zoom, eventClustering)
        : [],
    [filteredTheaterEvents, zoom, eventClustering, layers.theaterEvents],
  );

  useEffect(() => {
    if (!selectedEvent) return;
    if (!filteredTheaterEvents.includes(selectedEvent)) {
      setSelectedEvent(null);
    }
  }, [selectedEvent, filteredTheaterEvents]);

  const eventLegendItems = useMemo(() => {
    if (theaterLoading || filteredTheaterEvents.length === 0) return [];
    return (Object.entries(THEATER_EVENT_STYLE) as [string, { label: string; fill: string }][])
      .map(([key, { label, fill }]) => ({
        key,
        label,
        fill,
        count: filteredTheaterEvents.filter((e) => e.event_type === key).length,
      }))
      .filter((item) => item.count > 0);
  }, [filteredTheaterEvents, theaterLoading]);

  const deckLayers = useMemo(
    () =>
      buildTheaterDeckLayers({
        zoom,
        activeConflict,
        layerVisibility: layers,
        samRingLines,
        theaterDisplayItems,
        heatmapEvents,
        geointAnomalies,
        sigintAircraft,
        sigintShips,
        chokepointStatuses,
      }),
    [
      zoom,
      activeConflict,
      layers,
      samRingLines,
      theaterDisplayItems,
      heatmapEvents,
      geointAnomalies,
      sigintAircraft,
      sigintShips,
      chokepointStatuses,
    ],
  );

  const onDeckClick = useCallback(
    (info: PickingInfo) => {
      if (!info.object) return;
      const o = info.object as {
        pick?: TheaterPick;
        tooltip?: string;
      };
      if (o.pick) {
        const p = o.pick;
        if (p.kind === "cluster") {
          handleClusterZoomIn(p.lat, p.lon);
          return;
        }
        if (p.kind === "theater") {
          handleEventSelect(p.event);
          return;
        }
        if (p.kind === "aircraft") {
          handleAircraftSelect(p.data);
          return;
        }
        if (p.kind === "ship") {
          handleShipSelect(p.data);
          return;
        }
      }
    },
    [handleClusterZoomIn, handleEventSelect, handleAircraftSelect, handleShipSelect],
  );

  const onDeckHover = useCallback(
    (info: PickingInfo) => {
      if (!info.object) {
        handleTooltipHide();
        return;
      }
      const o = info.object as { pick?: TheaterPick; tooltip?: string };
      const layerId = info.layer?.id as string | undefined;
      if (o.pick?.kind === "theater") {
        const evt = o.pick.event;
        const style = THEATER_EVENT_STYLE[evt.event_type] ?? THEATER_EVENT_STYLE.other;
        const baseLabel = evt.label ?? evt.event_type;
        const locationPart = [evt.country, evt.admin1].filter(Boolean).join(", ");
        const content = locationPart ? `${baseLabel} · ${locationPart}` : baseLabel;
        setTooltipFromDeck(content, style.stroke, info);
        return;
      }
      if (o.pick?.kind === "cluster") {
        setTooltipFromDeck("Clustered area · click to zoom in", "hsl(var(--primary))", info);
        return;
      }
      if (o.pick?.kind === "aircraft") {
        const ac = o.pick.data;
        const content = ac.category ? `${ac.flight} · ${ac.category}` : ac.flight;
        setTooltipFromDeck(content, SIGINT_AIR_COLOR, info);
        return;
      }
      if (o.pick?.kind === "ship") {
        const sh = o.pick.data;
        const content = sh.type ? `${sh.name} · ${sh.type}` : sh.name;
        setTooltipFromDeck(content, SIGINT_SEA_COLOR, info);
        return;
      }
      if (typeof o.tooltip === "string") {
        let color = "hsl(210 90% 62%)";
        if (layerId?.startsWith("chokepoints")) color = "hsl(200 70% 50%)";
        else if (layerId === "bases-nuclear") color = "hsl(43 95% 56%)";
        else if (layerId === "geoint-anomalies") color = "var(--map-geoint)";
        setTooltipFromDeck(o.tooltip, color, info);
        return;
      }
      handleTooltipHide();
    },
    [handleTooltipHide, setTooltipFromDeck],
  );

  return (
    <div ref={mapContainerRef} className="absolute inset-0" role="application" aria-label="Theater map, conflict region">
      <DeckGL
        viewState={viewState}
        onViewStateChange={onViewStateChange}
        controller={{ dragRotate: false, touchRotate: false }}
        layers={deckLayers}
        onClick={onDeckClick}
        onHover={onDeckHover}
        pickingRadius={12}
        style={{ width: "100%", height: "100%" }}
        getCursor={({ isDragging, isHovering }) =>
          isDragging ? "grabbing" : isHovering ? "pointer" : "grab"
        }
      >
        {MAPBOX_TOKEN ? (
          <MapboxMap mapboxAccessToken={MAPBOX_TOKEN} mapStyle={MAPBOX_STYLE} reuseMaps />
        ) : (
          <MapLibreMap mapLib={maplibregl} mapStyle={FALLBACK_MAP_STYLE} reuseMaps />
        )}
      </DeckGL>

      <MapTooltip tooltip={tooltip} />

      <div className="absolute top-2 right-2 flex flex-col gap-2 sm:gap-1 z-10 pointer-events-auto">
        <button
          type="button"
          onClick={() =>
            setViewState((vs) => ({
              ...vs,
              zoom: Math.min(vs.zoom * 1.5, 8),
            }))
          }
          className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 sm:w-6 sm:h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors touch-manipulation"
          aria-label="Zoom in"
        >
          <Plus size={12} />
        </button>
        <button
          type="button"
          onClick={() =>
            setViewState((vs) => ({
              ...vs,
              zoom: Math.max(vs.zoom / 1.5, 2),
            }))
          }
          className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 sm:w-6 sm:h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors touch-manipulation"
          aria-label="Zoom out"
        >
          <Minus size={12} />
        </button>
      </div>

      {selectedEvent && (
        <div className="absolute bottom-24 left-2 right-2 sm:left-auto sm:right-2 sm:max-w-xs sm:w-[280px] rounded-lg border border-border bg-card/95 backdrop-blur-sm shadow-lg p-3 space-y-2 max-h-[60vh] overflow-y-auto z-10 pointer-events-auto">
          <div className="flex items-center justify-between gap-2 min-w-0">
            <div className="flex flex-col min-w-0 flex-1">
              <span className="font-mono text-[11px] text-muted-foreground tracking-wider uppercase">
                Event detail
              </span>
              <span className="text-xs font-semibold truncate">
                {THEATER_EVENT_STYLE[selectedEvent.event_type]?.label ?? selectedEvent.event_type}
              </span>
            </div>
            <button
              type="button"
              aria-label="Close escalation details"
              className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 sm:h-6 sm:w-6 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 touch-manipulation flex-shrink-0"
              onClick={() => setSelectedEvent(null)}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          {selectedEvent.label && (
            <p className="text-[11px] leading-snug text-foreground/90">{selectedEvent.label}</p>
          )}
          {selectedEvent.sub_event_type != null && selectedEvent.sub_event_type !== "" && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
              <span className="text-muted-foreground">Detail</span>
              <span className="text-right text-foreground/90">{selectedEvent.sub_event_type}</span>
            </div>
          )}
          {(selectedEvent.country || selectedEvent.admin1) && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
              {selectedEvent.country && (
                <>
                  <span className="text-muted-foreground">Country</span>
                  <span className="text-right text-foreground/90">{selectedEvent.country}</span>
                </>
              )}
              {selectedEvent.admin1 && (
                <>
                  <span className="text-muted-foreground">Region</span>
                  <span className="text-right text-foreground/90">{selectedEvent.admin1}</span>
                </>
              )}
            </div>
          )}
          <div className="space-y-0.5">
            <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">Casualties</span>
            <div className="text-[11px] text-foreground/90">
              {selectedEvent.fatalities != null ||
              selectedEvent.deaths_civilians != null ||
              selectedEvent.deaths_a != null ||
              selectedEvent.deaths_b != null ? (
                <>
                  {selectedEvent.fatalities != null && (
                    <p>Total reported: {selectedEvent.fatalities} fatality/fatalities</p>
                  )}
                  {selectedEvent.deaths_civilians != null && (
                    <p>Civilian: {selectedEvent.deaths_civilians}</p>
                  )}
                  {(selectedEvent.deaths_a != null || selectedEvent.deaths_b != null) && (
                    <p>
                      Military/actors: {[selectedEvent.deaths_a, selectedEvent.deaths_b]
                        .filter((n): n is number => n != null)
                        .join(" / ")}
                      {selectedEvent.side_a != null && selectedEvent.side_b != null && (
                        <span className="text-muted-foreground">
                          {" "}
                          ({selectedEvent.side_a} / {selectedEvent.side_b})
                        </span>
                      )}
                    </p>
                  )}
                </>
              ) : selectedEvent.source === "FIRMS" ? (
                <p>No casualty data (satellite thermal anomaly only).</p>
              ) : (
                <p>No casualty data reported.</p>
              )}
            </div>
          </div>
          {(selectedEvent.actor1 != null ||
            selectedEvent.actor2 != null ||
            selectedEvent.side_a != null ||
            selectedEvent.side_b != null) && (
            <div className="space-y-0.5">
              <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">Actors</span>
              <p className="text-[11px] text-foreground/90">
                {selectedEvent.actor1 != null || selectedEvent.actor2 != null
                  ? [selectedEvent.actor1, selectedEvent.actor2].filter(Boolean).join(" · ")
                  : selectedEvent.side_a != null || selectedEvent.side_b != null
                    ? `${selectedEvent.side_a ?? "—"} vs ${selectedEvent.side_b ?? "—"}`
                    : "—"}
              </p>
            </div>
          )}
          {(selectedEvent.event_date != null || selectedEvent.date_start != null) && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
              <span className="text-muted-foreground">Date</span>
              <span className="text-right text-foreground/90">
                {selectedEvent.event_date ?? selectedEvent.date_start ?? "—"}
              </span>
            </div>
          )}
          <div className="space-y-0.5">
            <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">Reporting / context</span>
            <p className="text-[11px] text-foreground/90 leading-snug line-clamp-4">
              {selectedEvent.notes != null && selectedEvent.notes !== ""
                ? selectedEvent.notes
                : selectedEvent.source === "FIRMS"
                  ? "Satellite detection (VIIRS). No linked news reporting."
                  : "No additional reporting."}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <span>Source</span>
            <span className="text-right">{selectedEvent.source ?? "FIRMS/ACLED"}</span>
            <span>Confidence</span>
            <span className="text-right">{selectedEvent.confidence ?? "n/a"}</span>
            <span>Location</span>
            <span className="text-right">
              {selectedEvent.lon.toFixed(1)}°E · {selectedEvent.lat.toFixed(1)}°N
            </span>
          </div>
          {selectedEvent.url != null && selectedEvent.url !== "" && (
            <a
              href={selectedEvent.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-[11px] text-primary hover:underline"
            >
              {selectedEvent.source === "FIRMS" ? "Open EO Browser (satellite imagery)" : "Open source"}
              <span aria-hidden>↗</span>
            </a>
          )}
        </div>
      )}

      {selectedSigint && (
        <div
          className="absolute bottom-24 left-2 right-2 sm:left-auto sm:right-2 sm:max-w-xs sm:w-[260px] rounded-lg border border-border bg-card/95 backdrop-blur-sm shadow-lg p-3 space-y-2 z-10 pointer-events-auto"
          style={
            selectedSigint.type === "aircraft"
              ? { borderColor: SIGINT_AIR_COLOR }
              : { borderColor: SIGINT_SEA_COLOR }
          }
        >
          <div className="flex items-center justify-between gap-2 min-w-0">
            <div className="flex flex-col min-w-0 flex-1">
              <span className="font-mono text-[11px] text-muted-foreground tracking-wider uppercase">
                Track detail
              </span>
              <span className="text-xs font-semibold truncate">
                {selectedSigint.type === "aircraft"
                  ? selectedSigint.data.flight
                  : selectedSigint.data.name}
              </span>
            </div>
            <button
              type="button"
              aria-label="Close track details"
              className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 sm:h-6 sm:w-6 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 touch-manipulation flex-shrink-0"
              onClick={() => setSelectedSigint(null)}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <span>Type</span>
            <span className="text-right">
              {selectedSigint.type === "aircraft"
                ? (selectedSigint.data.category ?? "—")
                : (selectedSigint.data.type ?? "—")}
            </span>
            {selectedSigint.type === "aircraft" && (selectedSigint.data as SigintAircraft).country && (
              <>
                <span>Country</span>
                <span className="text-right">{(selectedSigint.data as SigintAircraft).country}</span>
              </>
            )}
            <span>Location</span>
            <span className="text-right">
              {selectedSigint.data.lon.toFixed(1)}E · {selectedSigint.data.lat.toFixed(1)}N
            </span>
          </div>
        </div>
      )}

      <div className="absolute bottom-12 left-2 right-2 md:right-auto max-w-full overflow-x-auto overflow-y-hidden flex gap-2 flex-nowrap pb-1 md:overflow-visible md:flex-wrap md:gap-x-3 md:gap-y-2 md:pb-0 overflow-x-auto-touch items-center z-10 pointer-events-auto">
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground hidden sm:inline w-10">Events</span>
          <button
            type="button"
            onClick={() => toggleLayer("theaterEvents")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Theater strike / FIRMS / ACLED event markers"
            aria-label={layers.theaterEvents ? "Hide theater event markers" : "Show theater event markers"}
          >
            <span
              className={`w-2.5 h-2.5 rounded-sm border ${layers.theaterEvents ? "bg-primary/40 border-primary" : "bg-muted/40 border-border"}`}
            />
            STRIKE
            {theaterLoading && layers.theaterEvents && <span className="animate-pulse">…</span>}
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("heatmap")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Conflict intensity from ACLED"
            aria-label={layers.heatmap ? "Hide heatmap layer" : "Show heatmap layer"}
          >
            <span
              className={`w-2.5 h-2.5 rounded-full border ${layers.heatmap ? "bg-red-500/60 border-red-500" : "bg-muted/40 border-border"}`}
            />
            HEAT
            {heatmapLoading && layers.heatmap && <span className="animate-pulse">…</span>}
          </button>
          <span className="text-[11px] font-mono text-muted-foreground ml-0.5">EXP</span>
          {(["6h", "24h", "48h", "7d", "all"] as ExplosionTimeRange[]).map((range) => {
            const isActive = explosionRange === range;
            return (
              <button
                key={range}
                type="button"
                onClick={() => setExplosionRange(range)}
                className={`px-1.5 py-0.5 rounded border text-[10px] font-mono uppercase transition-colors touch-manipulation ${
                  isActive
                    ? "bg-destructive/20 border-destructive/60 text-foreground"
                    : "bg-card/60 border-border/70 text-muted-foreground hover:text-foreground"
                }`}
                aria-label={`Show explosion events for ${range.toUpperCase()}`}
              >
                {range.toUpperCase()}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0 border-l border-border/50 pl-2">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground hidden sm:inline w-8">SAM</span>
          <button
            type="button"
            onClick={() => toggleLayer("samRings")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="SAM engagement zones"
            aria-label={layers.samRings ? "Hide SAM rings layer" : "Show SAM rings layer"}
          >
            <span
              className={`w-2.5 h-2.5 rounded-full border ${layers.samRings ? "border-destructive" : "border-border"}`}
              style={
                layers.samRings
                  ? { borderColor: "hsl(var(--destructive))", background: "hsl(var(--destructive) / 0.2)" }
                  : {}
              }
            />
            ZONES
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("militaryBases")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Military base overlay"
            aria-label={layers.militaryBases ? "Hide military base layer" : "Show military base layer"}
          >
            <span
              className="w-2.5 h-2.5 border"
              style={
                layers.militaryBases
                  ? { borderColor: "hsl(210 90% 62%)", background: "hsl(210 90% 62% / 0.25)" }
                  : { borderColor: "hsl(var(--border))" }
              }
            />
            MB
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("nuclearFacilities")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Nuclear facility overlay"
            aria-label={layers.nuclearFacilities ? "Hide nuclear facility layer" : "Show nuclear facility layer"}
          >
            <span
              className="w-2.5 h-2.5 rounded-full border"
              style={
                layers.nuclearFacilities
                  ? { borderColor: "hsl(43 95% 56%)", background: "hsl(43 95% 56% / 0.25)" }
                  : { borderColor: "hsl(var(--border))" }
              }
            />
            NUC
          </button>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0 border-l border-border/50 pl-2">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground hidden sm:inline">Trade</span>
          <button
            type="button"
            onClick={() => toggleLayer("airRoutes")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Main air corridors"
            aria-label={layers.airRoutes ? "Hide air corridors layer" : "Show air corridors layer"}
          >
            <svg width="12" height="10" viewBox="-1.2 -1 2.4 2" className="shrink-0" style={{ color: layers.airRoutes ? "hsl(210 80% 55%)" : undefined }}>
              <polygon points="0,-1 0.65,0.35 0.45,1 0,0.55 -0.45,1 -1.2,0.35" fill="currentColor" stroke="currentColor" strokeWidth="0.15" />
            </svg>
            AIR
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("seaLanes")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Sea lanes"
            aria-label={layers.seaLanes ? "Hide sea lanes layer" : "Show sea lanes layer"}
          >
            <svg width="12" height="10" viewBox="-1.2 -0.5 2.4 1.2" className="shrink-0" style={{ color: layers.seaLanes ? "hsl(160 70% 45%)" : undefined }}>
              <path d="M -1.1 0.25 L -0.6 0.5 L 1 0.5 L 1.2 0.2 L 0.8 -0.1 L -0.9 -0.05 Z" fill="currentColor" stroke="currentColor" strokeWidth="0.1" />
            </svg>
            SEA
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("chokepoints")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Chokepoint zones"
            aria-label={layers.chokepoints ? "Hide chokepoints layer" : "Show chokepoints layer"}
          >
            <span
              className="w-2.5 h-2.5 rounded-sm border"
              style={
                layers.chokepoints
                  ? { borderColor: "hsl(200 70% 50%)", background: "hsl(200 70% 50% / 0.25)" }
                  : { borderColor: "hsl(var(--border))" }
              }
            />
            CHP
          </button>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0 border-l border-border/50 pl-2">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground hidden sm:inline w-8">Intel</span>
          <button
            type="button"
            onClick={() => toggleLayer("geoint")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            aria-label={layers.geoint ? "Hide GEOINT layer" : "Show GEOINT layer"}
          >
            <span style={{ color: layers.geoint ? "var(--map-geoint)" : undefined }}>△</span>
            GEOINT
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("sigint")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Live tracks: Air / Sea"
            aria-label={layers.sigint ? "Hide SIGINT layer (air and sea tracks)" : "Show SIGINT layer (air and sea tracks)"}
          >
            <svg width="12" height="10" viewBox="-1.2 -1 2.4 2" className="shrink-0" style={{ color: layers.sigint ? SIGINT_AIR_COLOR : undefined }}>
              <polygon points="0,-1 0.65,0.35 0.45,1 0,0.55 -0.45,1 -1.2,0.35" fill="currentColor" stroke="currentColor" strokeWidth="0.15" />
            </svg>
            <svg width="12" height="10" viewBox="-1.2 -0.5 2.4 1.2" className="shrink-0" style={{ color: layers.sigint ? SIGINT_SEA_COLOR : undefined }}>
              <path d="M -1.1 0.25 L -0.6 0.5 L 1 0.5 L 1.2 0.2 L 0.8 -0.1 L -0.9 -0.05 Z" fill="currentColor" stroke="currentColor" strokeWidth="0.1" />
            </svg>
            SIGINT
          </button>
        </div>
        {(layers.airRoutes || layers.seaLanes) && (
          <div className="flex items-center gap-2 flex-wrap">
            {layers.airRoutes && (
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: "hsl(210 80% 55%)" }} title="Air corridors" />
                <span className="text-[11px] font-mono text-muted-foreground">Air corridors</span>
              </div>
            )}
            {layers.seaLanes && (
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: "hsl(160 70% 45%)" }} title="Sea lanes" />
                <span className="text-[11px] font-mono text-muted-foreground">Sea lanes</span>
              </div>
            )}
          </div>
        )}
        {eventLegendItems.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            {eventLegendItems.map(({ key, label, fill }) => (
              <div key={key} className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: fill }} title={label} />
                <span className="text-[11px] font-mono text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {(geointAnomalies.length > 0 ||
        sigintAircraft.length > 0 ||
        sigintShips.length > 0 ||
        (layers.theaterEvents && filteredTheaterEvents.length > 0)) && (
        <div className="absolute top-2 left-2 flex items-center gap-2 bg-card/80 border border-border/50 rounded px-2 py-1 z-10 pointer-events-none">
          <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          <span className="text-[11px] font-mono text-muted-foreground">
            {layers.theaterEvents && filteredTheaterEvents.length > 0 && `${filteredTheaterEvents.length} STRIKES`}
            {layers.theaterEvents &&
              filteredTheaterEvents.length > 0 &&
              (geointAnomalies.length > 0 || sigintAircraft.length > 0 || sigintShips.length > 0) &&
              " · "}
            {geointAnomalies.length > 0 && `${geointAnomalies.length} THERMAL`}
            {geointAnomalies.length > 0 && (sigintAircraft.length > 0 || sigintShips.length > 0) && " · "}
            {sigintAircraft.length > 0 && `${sigintAircraft.length} AC`}
            {sigintAircraft.length > 0 && sigintShips.length > 0 && " · "}
            {sigintShips.length > 0 && `${sigintShips.length} SHIPS`}
          </span>
        </div>
      )}

      {(theaterError || heatmapError) && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 flex items-center gap-2 bg-destructive/90 text-destructive-foreground rounded px-3 py-1.5 shadow-lg z-10 pointer-events-none">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span className="text-[11px] font-mono">{theaterError ?? heatmapError}</span>
        </div>
      )}

      {theaterLoading && <MapLoadingSkeleton />}
    </div>
  );
}

export const TheaterMap = memo(TheaterMapInner);

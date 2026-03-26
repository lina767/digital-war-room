import { useEffect, useState, useCallback, useMemo, memo, useRef } from "react";
import { X, AlertTriangle } from "lucide-react";
import type { PickingInfo } from "@deck.gl/core";
import { MapContainer } from "@/features/theater-map/components/MapContainer";
import { LayerControls, type StrikeTimeRange } from "@/features/theater-map/components/LayerControls";
import { MapTooltip, type MapTooltipData } from "@/features/theater-map/components/MapTooltip";
import { useMapLayers } from "@/features/theater-map/hooks/useMapLayers";
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
  THEATER_STRIKE_LIKE_TYPES,
  inferStrikeAttribution,
  STRIKE_ATTRIBUTION_STYLE,
  strikeMarkerColors,
  type GeointAnomaly,
  type SigintAircraft,
  type SigintShip,
} from "./mapConfig";
import { MapLoadingSkeleton } from "@/components/ui/skeleton";
import { SAM_RINGS, circlePoints } from "./mapOverlaysData";
import { buildTheaterDeckLayers, type TheaterPick } from "./theaterDeckLayers";
import { buildTheaterDisplayItems } from "./theaterMapCluster";

/* ------------------------------------------------------------------ */
/*  Types / helpers                                                    */
/* ------------------------------------------------------------------ */

function parseEventTimestamp(value?: string): number | null {
  if (!value) return null;
  const raw = value.trim();
  if (!raw) return null;

  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(raw);
  const normalized = isDateOnly ? `${raw}T00:00:00Z` : raw;
  const parsed = Date.parse(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Time window for strike-like events (airstrike, missile, etc.); fire/other stay visible unless undated. */
function withinStrikeTimeRange(evt: TheaterEvent, range: StrikeTimeRange): boolean {
  if (range === "all") return true;
  if (!THEATER_STRIKE_LIKE_TYPES.has(evt.event_type)) return true;

  const hoursByRange: Record<Exclude<StrikeTimeRange, "all">, number> = {
    "6h": 6,
    "24h": 24,
    "48h": 48,
    "7d": 7 * 24,
  };

  const timestamp = parseEventTimestamp(evt.event_date ?? evt.date_start);
  if (timestamp == null) return true;

  const cutoff = Date.now() - hoursByRange[range] * 60 * 60 * 1000;
  return timestamp >= cutoff;
}

/** Carto vector style – used when `VITE_MAPBOX_TOKEN` is not set (no Mapbox map load). */
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
  const { layers, toggleLayer } = useMapLayers();

  const [selectedEvent, setSelectedEvent] = useState<TheaterEvent | null>(null);
  const [selectedSigint, setSelectedSigint] = useState<
    { type: "aircraft"; data: SigintAircraft } | { type: "ship"; data: SigintShip } | null
  >(null);
  const [strikeTimeRange, setStrikeTimeRange] = useState<StrikeTimeRange>("7d");
  /** Off: no green cluster halos; all strikes render as individual markers (WebGL). */
  const eventClustering = false;
  const [tooltip, setTooltip] = useState<MapTooltipData | null>(null);

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

  const onViewStateChange = useCallback(
    ({ viewState: vs }: { viewState: typeof viewState }) => {
      const z = Math.min(Math.max(vs.zoom, 2), 8);
      // Keep theater map in strict 2D to avoid perspective distortion on markers.
      setViewState({ ...vs, zoom: z, pitch: 0, bearing: 0 });
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
    setStrikeTimeRange("7d");
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
    () => theaterEvents.filter((evt) => withinStrikeTimeRange(evt, strikeTimeRange)),
    [theaterEvents, strikeTimeRange],
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

  const attributionLegendItems = useMemo(() => {
    if (theaterLoading || filteredTheaterEvents.length === 0) return [];
    const keys = ["us", "israel", "axis"] as const;
    return keys
      .map((key) => ({
        key,
        label: STRIKE_ATTRIBUTION_STYLE[key].label,
        fill: STRIKE_ATTRIBUTION_STYLE[key].fill,
        count: filteredTheaterEvents.filter((e) => inferStrikeAttribution(e) === key).length,
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
    [handleEventSelect, handleAircraftSelect, handleShipSelect],
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
        const attr = inferStrikeAttribution(evt);
        const attrHint =
          attr !== "unknown" ? ` · ${STRIKE_ATTRIBUTION_STYLE[attr].label}` : "";
        const baseLabel = evt.label ?? evt.event_type;
        const locationPart = [evt.country, evt.admin1].filter(Boolean).join(", ");
        const content = (locationPart ? `${baseLabel} · ${locationPart}` : baseLabel) + attrHint;
        const { stroke } = strikeMarkerColors(evt);
        const border = `rgba(${stroke[0]},${stroke[1]},${stroke[2]},${stroke[3] / 255})`;
        setTooltipFromDeck(content, border, info);
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

  const selectedStrikeAttr = selectedEvent != null ? inferStrikeAttribution(selectedEvent) : "unknown";

  return (
    <div className="absolute inset-0">
      <MapContainer
        containerRef={mapContainerRef}
        viewState={viewState}
        onViewStateChange={onViewStateChange}
        deckLayers={deckLayers}
        onDeckClick={onDeckClick}
        onDeckHover={onDeckHover}
        mapboxToken={MAPBOX_TOKEN}
        mapboxStyle={MAPBOX_STYLE}
        fallbackMapStyle={FALLBACK_MAP_STYLE}
      />

      <MapTooltip tooltip={tooltip} />

      <LayerControls
        layers={layers}
        toggleLayer={toggleLayer}
        strikeTimeRange={strikeTimeRange}
        onStrikeTimeRangeChange={setStrikeTimeRange}
        theaterLoading={theaterLoading}
        heatmapLoading={heatmapLoading}
        eventLegendItems={eventLegendItems}
        attributionLegendItems={attributionLegendItems}
        onZoomIn={() =>
          setViewState((vs) => ({
            ...vs,
            zoom: Math.min(vs.zoom * 1.5, 8),
          }))
        }
        onZoomOut={() =>
          setViewState((vs) => ({
            ...vs,
            zoom: Math.max(vs.zoom / 1.5, 2),
          }))
        }
        sigintAirColor={SIGINT_AIR_COLOR}
        sigintSeaColor={SIGINT_SEA_COLOR}
      />

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
          {selectedStrikeAttr !== "unknown" && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
              <span className="text-muted-foreground">Map attribution</span>
              <span className="text-right text-foreground/90">
                {STRIKE_ATTRIBUTION_STYLE[selectedStrikeAttr].label}
              </span>
            </div>
          )}
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
                    ? `${selectedEvent.side_a ?? "–"} vs ${selectedEvent.side_b ?? "–"}`
                    : "–"}
              </p>
            </div>
          )}
          {(selectedEvent.event_date != null || selectedEvent.date_start != null) && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
              <span className="text-muted-foreground">Date</span>
              <span className="text-right text-foreground/90">
                {selectedEvent.event_date ?? selectedEvent.date_start ?? "–"}
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
                ? (selectedSigint.data.category ?? "–")
                : (selectedSigint.data.type ?? "–")}
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

import { useEffect, useState, useCallback, useMemo, useReducer, memo, useRef } from "react";
import { Plus, Minus, X, AlertTriangle } from "lucide-react";
import {
  ComposableMap,
  Geographies,
  Geography,
  Line,
  Marker,
  ZoomableGroup,
} from "react-simple-maps";
import { getConflictEvents, getTheaterEvents, type ConflictEventForHeatmap, type TheaterEvent } from "@/lib/api";
import {
  GEO_URL,
  CONFLICT_CENTERS,
  matchConflict,
  hasOverlayDataForConflict,
  THEATER_EVENT_STYLE,
  type GeointAnomaly,
  type SigintAircraft,
  type SigintShip,
} from "./mapConfig";
import { MapLoadingSkeleton } from "@/components/ui/skeleton";
import { SAM_RINGS, AIR_ROUTES, SEA_LANES, CHOKEPOINT_ZONES, circlePoints } from "./mapOverlaysData";

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
  geoint: boolean;
  sigint: boolean;
  heatmap: boolean;
  samRings: boolean;
  airRoutes: boolean;
  seaLanes: boolean;
  chokepoints: boolean;
}

type LayerAction = { type: "TOGGLE"; layer: keyof LayerVisibility };
type ExplosionTimeRange = "6h" | "24h" | "48h" | "7d" | "all";

const INITIAL_LAYERS: LayerVisibility = {
  geoint: true,
  sigint: true,
  heatmap: false,
  samRings: false,
  airRoutes: true,
  seaLanes: true,
  chokepoints: true,
};

function layerReducer(state: LayerVisibility, action: LayerAction): LayerVisibility {
  return { ...state, [action.layer]: !state[action.layer] };
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Logarithmic marker scale — visually consistent across zoom 2..8 */
function markerScale(zoom: number): number {
  return Math.max(0.15, 1 / Math.sqrt(zoom));
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

/* ------------------------------------------------------------------ */
/*  Shape registry                                                     */
/* ------------------------------------------------------------------ */

type ShapeRenderer = (
  r: number,
  sw: number,
  style: { fill: string; stroke: string },
) => React.JSX.Element;

const EVENT_SHAPES: Record<string, ShapeRenderer> = {
  airstrike: (r, sw, st) => (
    <polygon
      points={`0,${-r * 1.2} ${r * 0.7},${r * 0.4} ${r * 0.5},${r} 0,${r * 0.6} ${-r * 0.5},${r} ${-r * 1.2},${r * 0.4}`}
      fill={st.fill}
      stroke={st.stroke}
      strokeWidth={sw}
    />
  ),
  missile: (r, sw, st) => (
    <polygon
      points={`0,${-r * 1.4} ${-r * 0.45},${r} ${r * 0.45},${r}`}
      fill={st.fill}
      stroke={st.stroke}
      strokeWidth={sw}
    />
  ),
  drone: (r, sw, st) => (
    <polygon
      points={`0,${-r} ${r},0 0,${r} ${-r},0`}
      fill={st.fill}
      stroke={st.stroke}
      strokeWidth={sw}
    />
  ),
  naval: (r, sw, st) => (
    <g fill={st.fill} stroke={st.stroke} strokeWidth={sw * 1.2}>
      <circle r={r * 0.5} fill="none" />
      <line x1={0} y1={-r * 0.5} x2={0} y2={r * 0.8} />
      <path d={`M ${-r * 0.6} ${r * 0.5} L ${r * 0.6} ${r * 0.5}`} fill="none" />
    </g>
  ),
};

const DEFAULT_SHAPE: ShapeRenderer = (r, sw, st) => (
  <circle r={r * 0.7} fill={st.fill} stroke={st.stroke} strokeWidth={sw} />
);

/* ------------------------------------------------------------------ */
/*  Memoized layer components                                          */
/* ------------------------------------------------------------------ */

const TheaterGeographies = memo(() => (
  <Geographies geography={GEO_URL}>
    {({ geographies }) =>
      geographies.map((geo) => (
        <Geography
          key={geo.rsmKey}
          geography={geo}
          fill="hsl(var(--foreground) / 0.15)"
          stroke="hsl(var(--primary) / 0.35)"
          strokeWidth={0.4}
          style={{
            default: { outline: "none" },
            hover: { outline: "none", fill: "hsl(var(--foreground) / 0.22)" },
            pressed: { outline: "none" },
          }}
        />
      ))
    }
  </Geographies>
));
TheaterGeographies.displayName = "TheaterGeographies";

/* ---- HeatmapLayer ------------------------------------------------ */

const HEATMAP_EVENT_COLORS: Record<string, string> = {
  battles: "#dc2626",
  protests: "#eab308",
  explosions: "#ea580c",
  riots: "#b45309",
  violence_against_civilians: "#b91c1c",
  strategic_development: "#6b7280",
};

interface HeatmapLayerProps {
  events: ConflictEventForHeatmap[];
  s: number;
  onTooltipShow?: (content: string, color: string, e: React.MouseEvent) => void;
  onTooltipHide?: () => void;
}

const HeatmapLayer = memo(function HeatmapLayer({ events, s, onTooltipShow, onTooltipHide }: HeatmapLayerProps) {
  const valid = useMemo(
    () => events.filter((e) => typeof e.lat === "number" && typeof e.lon === "number" && isFinite(e.lat) && isFinite(e.lon)),
    [events],
  );
  const markers = useMemo(
    () =>
      valid.map((evt, i) => {
        const r = (2 + (evt.intensity ?? 0) * 5) * s;
        const opacity = 0.15 + (evt.intensity ?? 0) * 0.35;
        const eventType = (evt.event_type ?? "").toLowerCase().replace(/\s+/g, "_");
        const fill = HEATMAP_EVENT_COLORS[eventType] ?? "#dc2626";
        const stroke = fill + "99";
        const parts: string[] = [];
        if (evt.event_type) parts.push(evt.event_type);
        if (evt.fatalities != null && evt.fatalities > 0) parts.push(`Fatalities: ${evt.fatalities}`);
        if (evt.actor1 || evt.actor2) parts.push([evt.actor1, evt.actor2].filter(Boolean).join(" vs "));
        if (evt.event_date) parts.push(evt.event_date);
        if (evt.notes) parts.push(evt.notes);
        const tooltipContent = parts.join(" · ");
        return (
          <Marker
            key={`heat-${evt.lat.toFixed(4)}-${evt.lon.toFixed(4)}-${i}`}
            coordinates={[evt.lon, evt.lat]}
          >
            <circle
              r={r}
              fill={fill}
              fillOpacity={opacity}
              stroke={stroke}
              strokeWidth={0.2 * s}
              pointerEvents={onTooltipShow ? "auto" : "none"}
              onMouseEnter={onTooltipShow && tooltipContent ? (e) => onTooltipShow(tooltipContent, fill, e) : undefined}
              onMouseLeave={onTooltipHide}
              style={onTooltipShow ? { cursor: "pointer" } : undefined}
            />
          </Marker>
        );
      }),
    [valid, s, onTooltipShow, onTooltipHide],
  );
  return <>{markers}</>;
});

/* ---- TheaterEventsLayer ------------------------------------------ */

interface TheaterEventsLayerProps {
  events: TheaterEvent[];
  s: number;
  onTooltipShow: (content: string, color: string, e: React.MouseEvent) => void;
  onTooltipHide: () => void;
  onEventSelect: (evt: TheaterEvent) => void;
}

const TheaterEventsLayer = memo(function TheaterEventsLayer({
  events,
  s,
  onTooltipShow,
  onTooltipHide,
  onEventSelect,
}: TheaterEventsLayerProps) {
  const valid = useMemo(
    () => events.filter((e) => typeof e.lat === "number" && typeof e.lon === "number" && isFinite(e.lat) && isFinite(e.lon)),
    [events],
  );
  const markers = useMemo(
    () =>
      valid.map((evt, i) => {
        const style = THEATER_EVENT_STYLE[evt.event_type] ?? THEATER_EVENT_STYLE.other;
        const r = 3 * s;
        const sw = 0.25 * s;
        const shape = (EVENT_SHAPES[evt.event_type] ?? DEFAULT_SHAPE)(r, sw, style);
        const baseLabel = evt.label ?? evt.event_type;
        const locationPart = [evt.country, evt.admin1].filter(Boolean).join(", ");
        const tooltipContent = locationPart ? `${baseLabel} · ${locationPart}` : baseLabel;

        return (
          <Marker
            key={`theater-${evt.lat.toFixed(4)}-${evt.lon.toFixed(4)}-${evt.event_type}-${i}`}
            coordinates={[evt.lon, evt.lat]}
          >
            <g
              className="cursor-pointer"
              onClick={() => onEventSelect(evt)}
              onMouseEnter={(e) => onTooltipShow(tooltipContent, style.stroke, e)}
              onMouseLeave={onTooltipHide}
            >
              <circle
                className="theater-pulse"
                style={{ animationDelay: `${(i % 20) * 0.1}s` }}
                r={r * 2}
                fill="none"
                stroke={style.stroke}
                strokeWidth={0.3 * s}
              />
              {shape}
              {evt.country && (
                <text
                  y={r * 3.2}
                  textAnchor="middle"
                  fill="currentColor"
                  className="fill-foreground/80"
                  style={{ fontSize: `${Math.max(6, 8 * s)}px`, fontFamily: "system-ui, sans-serif", pointerEvents: "none" }}
                >
                  {evt.country}
                </text>
              )}
            </g>
          </Marker>
        );
      }),
    [valid, s, onTooltipShow, onTooltipHide, onEventSelect],
  );
  return <>{markers}</>;
});

/* ---- GeointLayer ------------------------------------------------- */

interface GeointLayerProps {
  anomalies: GeointAnomaly[];
  s: number;
  onTooltipShow: (content: string, color: string, e: React.MouseEvent) => void;
  onTooltipHide: () => void;
}

const GeointLayer = memo(function GeointLayer({
  anomalies,
  s,
  onTooltipShow,
  onTooltipHide,
}: GeointLayerProps) {
  const valid = useMemo(
    () => anomalies.filter((a) => typeof a.latitude === "number" && typeof a.longitude === "number" && isFinite(a.latitude) && isFinite(a.longitude)),
    [anomalies],
  );
  const markers = useMemo(
    () =>
      valid.map((anomaly, i) => {
        const intensity = anomaly.frp > 1000 ? 1 : anomaly.frp > 100 ? 0.7 : 0.4;
        const r = Math.min(3 + (anomaly.frp ?? 0) / 200, 8) * s;
        const label = `${anomaly.classification ?? "unknown"} · FRP ${Math.round(anomaly.frp ?? 0)} MW`;

        return (
          <Marker
            key={`geoint-${anomaly.latitude.toFixed(4)}-${anomaly.longitude.toFixed(4)}-${i}`}
            coordinates={[anomaly.longitude, anomaly.latitude]}
          >
            <g
              filter="url(#theater-glow-geoint)"
              className="cursor-pointer"
              onMouseEnter={(e) => onTooltipShow(label, "var(--map-geoint)", e)}
              onMouseLeave={onTooltipHide}
            >
              <circle
                className="geoint-pulse"
                style={{ animationDelay: `${(i % 15) * 0.17}s` }}
                r={r * 2.5}
                fill="none"
                stroke="var(--map-geoint)"
                strokeWidth={0.4 * s}
              />
              <polygon
                points={`0,${-r * 1.8} ${r * 1.2},${r * 0.9} ${-r * 1.2},${r * 0.9}`}
                fill={`rgba(255, ${Math.floor(68 + (1 - intensity) * 100)}, 0, ${0.7 + intensity * 0.3})`}
                stroke="var(--map-geoint-stroke)"
                strokeWidth={0.3 * s}
              />
            </g>
          </Marker>
        );
      }),
    [valid, s, onTooltipShow, onTooltipHide],
  );
  return <>{markers}</>;
});

/* ---- SIGINT Air icon: stilisierter Jet (Dreieck) ----------------- */
const SIGINT_AIR_COLOR = "var(--map-sigint-air)";
const SIGINT_AIR_STROKE = "var(--map-sigint-air-stroke)";
function SigintAirIcon({ r, s }: { r: number; s: number }) {
  return (
    <g fill={SIGINT_AIR_COLOR} stroke={SIGINT_AIR_STROKE} strokeWidth={0.25 * s}>
      <polygon
        points={`0,${-r * 1.15} ${r * 0.65},${r * 0.35} ${r * 0.45},${r} 0,${r * 0.55} ${-r * 0.45},${r} ${-r * 1.15},${r * 0.35}`}
      />
    </g>
  );
}

/* ---- SigintAircraftLayer ----------------------------------------- */

interface SigintAircraftLayerProps {
  aircraft: SigintAircraft[];
  s: number;
  onTooltipShow: (content: string, color: string, e: React.MouseEvent) => void;
  onTooltipHide: () => void;
  onAircraftSelect?: (ac: SigintAircraft) => void;
}

const SigintAircraftLayer = memo(function SigintAircraftLayer({
  aircraft,
  s,
  onTooltipShow,
  onTooltipHide,
  onAircraftSelect,
}: SigintAircraftLayerProps) {
  const valid = useMemo(
    () => aircraft.filter((a) => typeof a.lat === "number" && typeof a.lon === "number" && isFinite(a.lat) && isFinite(a.lon)),
    [aircraft],
  );
  const markers = useMemo(
    () =>
      valid.map((ac, i) => {
        const r = 3 * s;
        const tooltipContent = ac.category ? `${ac.flight} · ${ac.category}` : ac.flight;
        return (
          <Marker
            key={`ac-${ac.lat.toFixed(4)}-${ac.lon.toFixed(4)}-${ac.flight}`}
            coordinates={[ac.lon, ac.lat]}
          >
            <g
              className="cursor-pointer"
              onClick={() => onAircraftSelect?.(ac)}
              onMouseEnter={(e) => onTooltipShow(tooltipContent, SIGINT_AIR_COLOR, e)}
              onMouseLeave={onTooltipHide}
            >
              <circle
                className="sigint-air-pulse"
                style={{ animationDelay: `${(i % 15) * 0.12}s` }}
                r={r * 2}
                fill="none"
                stroke={SIGINT_AIR_COLOR}
                strokeWidth={0.3 * s}
              />
              <SigintAirIcon r={r} s={s} />
            </g>
          </Marker>
        );
      }),
    [valid, s, onTooltipShow, onTooltipHide, onAircraftSelect],
  );
  return <>{markers}</>;
});

/* ---- SIGINT Sea icon: stilisierte Schiff-Silhouette (Rumpf + Aufbauten) -- */
const SIGINT_SEA_COLOR = "var(--map-sigint-sea)";
const SIGINT_SEA_STROKE = "var(--map-sigint-sea-stroke)";
function SigintShipIcon({ r, s }: { r: number; s: number }) {
  return (
    <g fill={SIGINT_SEA_COLOR} stroke={SIGINT_SEA_STROKE} strokeWidth={0.25 * s}>
      {/* Rumpf */}
      <path
        d={`M ${-r * 1.1} ${r * 0.25} L ${-r * 0.6} ${r * 0.5} L ${r * 1} ${r * 0.5} L ${r * 1.2} ${r * 0.2} L ${r * 0.8} ${-r * 0.1} L ${-r * 0.9} ${-r * 0.05} Z`}
      />
      {/* Aufbau / Brücke */}
      <rect x={-r * 0.3} y={-r * 0.35} width={r * 0.5} height={r * 0.5} rx={r * 0.08} />
    </g>
  );
}

/* ---- SigintShipsLayer -------------------------------------------- */

interface SigintShipsLayerProps {
  ships: SigintShip[];
  s: number;
  onTooltipShow: (content: string, color: string, e: React.MouseEvent) => void;
  onTooltipHide: () => void;
  onShipSelect?: (ship: SigintShip) => void;
}

const SigintShipsLayer = memo(function SigintShipsLayer({
  ships,
  s,
  onTooltipShow,
  onTooltipHide,
  onShipSelect,
}: SigintShipsLayerProps) {
  const valid = useMemo(
    () => ships.filter((sh) => typeof sh.lat === "number" && typeof sh.lon === "number" && isFinite(sh.lat) && isFinite(sh.lon)),
    [ships],
  );
  const markers = useMemo(
    () =>
      valid.map((ship, i) => {
        const r = 3 * s;
        const tooltipContent = ship.type ? `${ship.name} · ${ship.type}` : ship.name;
        return (
          <Marker
            key={`ship-${ship.lat.toFixed(4)}-${ship.lon.toFixed(4)}-${ship.name}`}
            coordinates={[ship.lon, ship.lat]}
          >
            <g
              className="cursor-pointer"
              onClick={() => onShipSelect?.(ship)}
              onMouseEnter={(e) => onTooltipShow(tooltipContent, SIGINT_SEA_COLOR, e)}
              onMouseLeave={onTooltipHide}
            >
              <circle
                className="sigint-sea-pulse"
                style={{ animationDelay: `${(i % 15) * 0.12}s` }}
                r={r * 2}
                fill="none"
                stroke={SIGINT_SEA_COLOR}
                strokeWidth={0.3 * s}
              />
              <SigintShipIcon r={r} s={s} />
            </g>
          </Marker>
        );
      }),
    [valid, s, onTooltipShow, onTooltipHide, onShipSelect],
  );
  return <>{markers}</>;
});

/* ---- MapTooltip (HTML portal) ------------------------------------ */

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
  status: "OPEN" | "RESTRICTED" | "DISRUPTED";
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
  /* ---- layer visibility (useReducer instead of 6× useState) ------ */
  const [layers, dispatchLayers] = useReducer(layerReducer, INITIAL_LAYERS);
  const toggleLayer = useCallback(
    (layer: keyof LayerVisibility) => dispatchLayers({ type: "TOGGLE", layer }),
    [],
  );

  /* ---- core UI state --------------------------------------------- */
  const [selectedEvent, setSelectedEvent] = useState<TheaterEvent | null>(null);
  const [selectedSigint, setSelectedSigint] = useState<
    { type: "aircraft"; data: SigintAircraft } | { type: "ship"; data: SigintShip } | null
  >(null);
  const [explosionRange, setExplosionRange] = useState<ExplosionTimeRange>("7d");
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const [zoom, setZoom] = useState(4.73);
  const [center, setCenter] = useState<[number, number]>([54.0836, 31.7419]);

  /* ---- async data + error states --------------------------------- */
  const [theaterEvents, setTheaterEvents] = useState<TheaterEvent[]>([]);
  const [theaterLoading, setTheaterLoading] = useState(false);
  const [theaterError, setTheaterError] = useState<string | null>(null);

  const [heatmapEvents, setHeatmapEvents] = useState<ConflictEventForHeatmap[]>([]);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [heatmapError, setHeatmapError] = useState<string | null>(null);

  /* ---- derived: logarithmic marker scale ------------------------- */
  const s = markerScale(zoom);

  /* ---- tooltip with delay (150–200 ms) to reduce flicker --------- */
  const tooltipTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const TOOLTIP_DELAY_MS = 180;

  const handleTooltipShow = useCallback(
    (content: string, color: string, e: React.MouseEvent) => {
      if (tooltipTimeoutRef.current) {
        clearTimeout(tooltipTimeoutRef.current);
        tooltipTimeoutRef.current = null;
      }
      tooltipTimeoutRef.current = setTimeout(() => {
        tooltipTimeoutRef.current = null;
        setTooltip({ content, color, x: e.clientX, y: e.clientY });
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

  const handleMoveEnd = useCallback(({ coordinates, zoom: z }: { coordinates: [number, number]; zoom: number }) => {
    setCenter(coordinates);
    setZoom(z);
  }, []);

  /* ---- conflict center navigation -------------------------------- */
  useEffect(() => {
    if (!activeConflict) return;
    const key = matchConflict(activeConflict);
    if (key && CONFLICT_CENTERS[key]) {
      const { center: c, zoom: z } = CONFLICT_CENTERS[key];
      setCenter(c);
      setZoom(z);
    }
  }, [activeConflict]);

  useEffect(() => {
    setExplosionRange("7d");
  }, [activeConflict]);

  /* ---- heatmap data ---------------------------------------------- */
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

  /* ---- theater events data --------------------------------------- */
  useEffect(() => {
    if (!activeConflict) {
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
  }, [activeConflict]);

  /* ---- memoized overlay data ------------------------------------- */
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

  const airRouteLabels = useMemo(() => {
    if (!layers.airRoutes || !hasOverlayDataForConflict(activeConflict) || zoom < 4) return null;
    return AIR_ROUTES.map((route) => {
      const mid = route.coordinates[Math.floor(route.coordinates.length / 2)];
      return (
        <Marker key={`air-label-${route.id}`} coordinates={mid}>
          <text
            textAnchor="middle"
            fontSize={2.2}
            fill="hsl(210 80% 55% / 0.9)"
            style={{ fontFamily: "var(--font-mono)", fontWeight: 500 }}
          >
            {route.name}
          </text>
        </Marker>
      );
    });
  }, [layers.airRoutes, activeConflict, zoom]);

  const seaLaneLabels = useMemo(() => {
    if (!layers.seaLanes || !hasOverlayDataForConflict(activeConflict) || zoom < 4) return null;
    return SEA_LANES.map((lane) => {
      const mid = lane.coordinates[Math.floor(lane.coordinates.length / 2)];
      return (
        <Marker key={`sea-label-${lane.id}`} coordinates={mid}>
          <text
            textAnchor="middle"
            fontSize={2}
            fill="hsl(160 70% 45% / 0.9)"
            style={{ fontFamily: "var(--font-mono)", fontWeight: 500 }}
          >
            {lane.name}
          </text>
        </Marker>
      );
    });
  }, [layers.seaLanes, activeConflict, zoom]);

  /* ---- render ---------------------------------------------------- */
  return (
    <div className="absolute inset-0" role="application" aria-label="Theater map, conflict region">
      <ComposableMap
        projectionConfig={{ rotate: [-10, 0, 0], scale: 160 }}
        projection="geoNaturalEarth1"
        className="w-full h-full"
        style={{ width: "100%", height: "100%" }}
      >
        <defs>
          <filter id="theater-glow-geoint" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feFlood floodColor="var(--map-geoint)" floodOpacity="0.7" result="color" />
            <feComposite in="color" in2="blur" operator="in" result="shadow" />
            <feMerge>
              <feMergeNode in="shadow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <ZoomableGroup
          zoom={zoom}
          center={center}
          onMoveEnd={handleMoveEnd}
          minZoom={2}
          maxZoom={8}
        >
          <TheaterGeographies />

          {layers.samRings && hasOverlayDataForConflict(activeConflict) &&
            samRingLines.map((sam) => (
              <Line
                key={sam.id}
                coordinates={sam.coords}
                stroke="hsl(var(--destructive) / 0.6)"
                strokeWidth={0.5}
                fill="none"
                strokeDasharray="2 2"
              />
            ))}

          {layers.airRoutes && hasOverlayDataForConflict(activeConflict) &&
            AIR_ROUTES.map((route) => (
              <Line
                key={route.id}
                coordinates={route.coordinates}
                stroke="hsl(210 80% 55% / 0.85)"
                strokeWidth={0.8}
                fill="none"
                strokeDasharray="4 2"
              />
            ))}

          {airRouteLabels}

          {layers.seaLanes && hasOverlayDataForConflict(activeConflict) &&
            SEA_LANES.map((lane) => (
              <Line
                key={lane.id}
                coordinates={lane.coordinates}
                stroke="hsl(160 70% 45% / 0.85)"
                strokeWidth={0.75}
                fill="none"
                strokeDasharray="3 2"
              />
            ))}

          {seaLaneLabels}

          {layers.chokepoints &&
            CHOKEPOINT_ZONES.map((zone) => {
              const match = chokepointStatuses.find((cp) => cp.name === zone.name);
              const risk = match?.disruption_risk ?? 0;
              const fillColor =
                risk >= 70
                  ? "hsla(0, 70%, 50%, 0.18)"
                  : risk >= 40
                    ? "hsla(40, 80%, 50%, 0.15)"
                    : "hsla(160, 70%, 45%, 0.10)";
              const strokeColor =
                risk >= 70
                  ? "hsla(0, 70%, 50%, 0.5)"
                  : risk >= 40
                    ? "hsla(40, 80%, 50%, 0.4)"
                    : "hsla(160, 70%, 45%, 0.3)";
              const tooltipContent = match
                ? `${zone.name} · ${match.status} · Risk ${match.disruption_risk}%`
                : `${zone.name}`;
              return (
                <g
                  key={zone.id}
                  onMouseEnter={(e) => handleTooltipShow(tooltipContent, strokeColor, e)}
                  onMouseLeave={handleTooltipHide}
                  style={{ cursor: "pointer" }}
                >
                  <Line
                    coordinates={zone.vertices}
                    stroke={strokeColor}
                    strokeWidth={0.8}
                    fill={fillColor}
                  />
                </g>
              );
            })}

          {layers.heatmap && !heatmapLoading && (
            <HeatmapLayer
              events={heatmapEvents}
              s={s}
              onTooltipShow={handleTooltipShow}
              onTooltipHide={handleTooltipHide}
            />
          )}

          {!theaterLoading && (
            <TheaterEventsLayer
              events={filteredTheaterEvents}
              s={s}
              onTooltipShow={handleTooltipShow}
              onTooltipHide={handleTooltipHide}
              onEventSelect={handleEventSelect}
            />
          )}

          {layers.geoint && (
            <GeointLayer
              anomalies={geointAnomalies}
              s={s}
              onTooltipShow={handleTooltipShow}
              onTooltipHide={handleTooltipHide}
            />
          )}

          {layers.sigint && (
            <>
              <SigintAircraftLayer
                aircraft={sigintAircraft}
                s={s}
                onTooltipShow={handleTooltipShow}
                onTooltipHide={handleTooltipHide}
                onAircraftSelect={handleAircraftSelect}
              />
              <SigintShipsLayer
                ships={sigintShips}
                s={s}
                onTooltipShow={handleTooltipShow}
                onTooltipHide={handleTooltipHide}
                onShipSelect={handleShipSelect}
              />
            </>
          )}
        </ZoomableGroup>
      </ComposableMap>

      {/* HTML tooltip portal — single instance for all layers */}
      <MapTooltip tooltip={tooltip} />

      {/* Zoom controls – 44px touch targets on mobile, compact on desktop */}
      <div className="absolute top-2 right-2 flex flex-col gap-2 sm:gap-1">
        <button
          type="button"
          onClick={() => setZoom((z) => Math.min(z * 1.5, 8))}
          className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 sm:w-6 sm:h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors touch-manipulation"
          aria-label="Zoom in"
        >
          <Plus size={12} />
        </button>
        <button
          type="button"
          onClick={() => setZoom((z) => Math.max(z / 1.5, 2))}
          className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 sm:w-6 sm:h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors touch-manipulation"
          aria-label="Zoom out"
        >
          <Minus size={12} />
        </button>
      </div>

      {/* Escalation detail panel – full width with margin on small screens, 44px close on touch */}
      {selectedEvent && (
        <div className="absolute bottom-24 left-2 right-2 sm:left-auto sm:right-2 sm:max-w-xs sm:w-[280px] rounded-lg border border-border bg-card/95 backdrop-blur-sm shadow-lg p-3 space-y-2 max-h-[60vh] overflow-y-auto">
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
            <p className="text-[11px] leading-snug text-foreground/90">
              {selectedEvent.label}
            </p>
          )}
          {selectedEvent.sub_event_type != null && selectedEvent.sub_event_type !== "" && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
              <span className="text-muted-foreground">Detail</span>
              <span className="text-right text-foreground/90">{selectedEvent.sub_event_type}</span>
            </div>
          )}
          {/* Location: country / admin1 for aggregated data */}
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
          {/* Weekly event count for aggregated data */}
          {selectedEvent.events_count != null && selectedEvent.events_count > 0 && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
              <span className="text-muted-foreground">Events (week)</span>
              <span className="text-right text-foreground/90 font-semibold">{selectedEvent.events_count}</span>
            </div>
          )}
          {/* Casualties: always show – with data or fallback explanation */}
          <div className="space-y-0.5">
            <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">Casualties</span>
            <div className="text-[11px] text-foreground/90">
              {selectedEvent.fatalities != null || selectedEvent.deaths_civilians != null || selectedEvent.deaths_a != null || selectedEvent.deaths_b != null ? (
                <>
                  {selectedEvent.fatalities != null && (
                    <p>Total reported: {selectedEvent.fatalities} {selectedEvent.events_count ? `(week ${selectedEvent.event_date ?? "?"})` : "fatality/fatalities"}</p>
                  )}
                  {selectedEvent.deaths_civilians != null && (
                    <p>Civilian: {selectedEvent.deaths_civilians}</p>
                  )}
                  {(selectedEvent.deaths_a != null || selectedEvent.deaths_b != null) && (
                    <p>
                      Military/actors: {[selectedEvent.deaths_a, selectedEvent.deaths_b].filter((n): n is number => n != null).join(" / ")}
                      {selectedEvent.side_a != null && selectedEvent.side_b != null && (
                        <span className="text-muted-foreground"> ({selectedEvent.side_a} / {selectedEvent.side_b})</span>
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
          {/* Actors / sides */}
          {(selectedEvent.actor1 != null || selectedEvent.actor2 != null || selectedEvent.side_a != null || selectedEvent.side_b != null) && (
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
          {/* Date */}
          {(selectedEvent.event_date != null || selectedEvent.date_start != null) && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
              <span className="text-muted-foreground">Date</span>
              <span className="text-right text-foreground/90">{selectedEvent.event_date ?? selectedEvent.date_start ?? "—"}</span>
            </div>
          )}
          {/* Reporting / context: always show – notes or fallback */}
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
            <span className="text-right">{selectedEvent.lon.toFixed(1)}°E · {selectedEvent.lat.toFixed(1)}°N</span>
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

      {/* SIGINT track detail panel (aircraft / ship) – full width on small screens, 44px close on touch */}
      {selectedSigint && (
        <div
          className="absolute bottom-24 left-2 right-2 sm:left-auto sm:right-2 sm:max-w-xs sm:w-[260px] rounded-lg border border-border bg-card/95 backdrop-blur-sm shadow-lg p-3 space-y-2"
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

      {/* Layer toggle bar – horizontal scroll on small screens, wrap on md+ */}
      <div className="absolute bottom-12 left-2 right-2 md:right-auto max-w-full overflow-x-auto overflow-y-hidden flex gap-2 flex-nowrap pb-1 md:overflow-visible md:flex-wrap md:gap-3 md:pb-0 overflow-x-auto-touch">
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-[11px] font-mono text-muted-foreground">EXP</span>
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
          HEATMAP
          {heatmapLoading && layers.heatmap && <span className="animate-pulse">…</span>}
        </button>
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
          SAM
        </button>
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

      {/* Live feed indicator */}
      {(geointAnomalies.length > 0 || sigintAircraft.length > 0 || sigintShips.length > 0 || filteredTheaterEvents.length > 0) && (
        <div className="absolute top-2 left-2 flex items-center gap-2 bg-card/80 border border-border/50 rounded px-2 py-1">
          <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          <span className="text-[11px] font-mono text-muted-foreground">
            {filteredTheaterEvents.length > 0 && `${filteredTheaterEvents.length} STRIKES`}
            {filteredTheaterEvents.length > 0 && (geointAnomalies.length > 0 || sigintAircraft.length > 0 || sigintShips.length > 0) && " · "}
            {geointAnomalies.length > 0 && `${geointAnomalies.length} THERMAL`}
            {geointAnomalies.length > 0 && (sigintAircraft.length > 0 || sigintShips.length > 0) && " · "}
            {sigintAircraft.length > 0 && `${sigintAircraft.length} AC`}
            {sigintAircraft.length > 0 && sigintShips.length > 0 && " · "}
            {sigintShips.length > 0 && `${sigintShips.length} SHIPS`}
          </span>
        </div>
      )}

      {/* Error banner */}
      {(theaterError || heatmapError) && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 flex items-center gap-2 bg-destructive/90 text-destructive-foreground rounded px-3 py-1.5 shadow-lg">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span className="text-[11px] font-mono">{theaterError ?? heatmapError}</span>
        </div>
      )}

      {/* Loading overlay */}
      {theaterLoading && <MapLoadingSkeleton />}
    </div>
  );
}

export const TheaterMap = memo(TheaterMapInner);

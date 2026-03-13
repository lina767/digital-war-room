import { useEffect, useState, useCallback, useMemo, useReducer, memo } from "react";
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
  THEATER_EVENT_STYLE,
  type GeointAnomaly,
  type SigintAircraft,
  type SigintShip,
} from "./mapConfig";
import { SAM_RINGS, AIR_ROUTES, SEA_LANES, circlePoints } from "./mapOverlaysData";

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
}

type LayerAction = { type: "TOGGLE"; layer: keyof LayerVisibility };

const INITIAL_LAYERS: LayerVisibility = {
  geoint: true,
  sigint: true,
  heatmap: false,
  samRings: false,
  airRoutes: false,
  seaLanes: false,
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

interface HeatmapLayerProps {
  events: ConflictEventForHeatmap[];
  s: number;
}

const HeatmapLayer = memo(function HeatmapLayer({ events, s }: HeatmapLayerProps) {
  const valid = useMemo(
    () => events.filter((e) => typeof e.lat === "number" && typeof e.lon === "number" && isFinite(e.lat) && isFinite(e.lon)),
    [events],
  );
  const markers = useMemo(
    () =>
      valid.map((evt, i) => {
        const r = (2 + (evt.intensity ?? 0) * 5) * s;
        const opacity = 0.15 + (evt.intensity ?? 0) * 0.35;
        return (
          <Marker
            key={`heat-${evt.lat.toFixed(4)}-${evt.lon.toFixed(4)}-${i}`}
            coordinates={[evt.lon, evt.lat]}
          >
            <circle
              r={r}
              fill="#dc2626"
              fillOpacity={opacity}
              stroke="rgba(220,38,38,0.4)"
              strokeWidth={0.2 * s}
              pointerEvents="none"
            />
          </Marker>
        );
      }),
    [valid, s],
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

        return (
          <Marker
            key={`theater-${evt.lat.toFixed(4)}-${evt.lon.toFixed(4)}-${evt.event_type}-${i}`}
            coordinates={[evt.lon, evt.lat]}
          >
            <g
              className="cursor-pointer"
              onClick={() => onEventSelect(evt)}
              onMouseEnter={(e) => onTooltipShow(evt.label ?? evt.event_type, style.stroke, e)}
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
              onMouseEnter={(e) => onTooltipShow(label, "#ff4400", e)}
              onMouseLeave={onTooltipHide}
            >
              <circle
                className="geoint-pulse"
                style={{ animationDelay: `${(i % 15) * 0.17}s` }}
                r={r * 2.5}
                fill="none"
                stroke="#ff4400"
                strokeWidth={0.4 * s}
              />
              <polygon
                points={`0,${-r * 1.8} ${r * 1.2},${r * 0.9} ${-r * 1.2},${r * 0.9}`}
                fill={`rgba(255, ${Math.floor(68 + (1 - intensity) * 100)}, 0, ${0.7 + intensity * 0.3})`}
                stroke="#ff2200"
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

/* ---- SigintAircraftLayer ----------------------------------------- */

interface SigintAircraftLayerProps {
  aircraft: SigintAircraft[];
  s: number;
  onTooltipShow: (content: string, color: string, e: React.MouseEvent) => void;
  onTooltipHide: () => void;
}

const SigintAircraftLayer = memo(function SigintAircraftLayer({
  aircraft,
  s,
  onTooltipShow,
  onTooltipHide,
}: SigintAircraftLayerProps) {
  const valid = useMemo(
    () => aircraft.filter((a) => typeof a.lat === "number" && typeof a.lon === "number" && isFinite(a.lat) && isFinite(a.lon)),
    [aircraft],
  );
  const markers = useMemo(
    () =>
      valid.map((ac) => (
        <Marker
          key={`ac-${ac.lat.toFixed(4)}-${ac.lon.toFixed(4)}-${ac.flight}`}
          coordinates={[ac.lon, ac.lat]}
        >
          <g
            className="cursor-pointer"
            onMouseEnter={(e) => onTooltipShow(ac.flight, "#60a5fa", e)}
            onMouseLeave={onTooltipHide}
          >
            <text
              textAnchor="middle"
              fontSize={12 * s}
              fill="#60a5fa"
              opacity={0.9}
              style={{ userSelect: "none" }}
            >
              ✈
            </text>
          </g>
        </Marker>
      )),
    [valid, s, onTooltipShow, onTooltipHide],
  );
  return <>{markers}</>;
});

/* ---- SigintShipsLayer -------------------------------------------- */

interface SigintShipsLayerProps {
  ships: SigintShip[];
  s: number;
  onTooltipShow: (content: string, color: string, e: React.MouseEvent) => void;
  onTooltipHide: () => void;
}

const SigintShipsLayer = memo(function SigintShipsLayer({
  ships,
  s,
  onTooltipShow,
  onTooltipHide,
}: SigintShipsLayerProps) {
  const valid = useMemo(
    () => ships.filter((sh) => typeof sh.lat === "number" && typeof sh.lon === "number" && isFinite(sh.lat) && isFinite(sh.lon)),
    [ships],
  );
  const markers = useMemo(
    () =>
      valid.map((ship) => (
        <Marker
          key={`ship-${ship.lat.toFixed(4)}-${ship.lon.toFixed(4)}-${ship.name}`}
          coordinates={[ship.lon, ship.lat]}
        >
          <g
            className="cursor-pointer"
            onMouseEnter={(e) => onTooltipShow(ship.name, "#34d399", e)}
            onMouseLeave={onTooltipHide}
          >
            <text
              textAnchor="middle"
              fontSize={11 * s}
              fill="#34d399"
              opacity={0.9}
              style={{ userSelect: "none" }}
            >
              ⚓
            </text>
          </g>
        </Marker>
      )),
    [valid, s, onTooltipShow, onTooltipHide],
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

export interface TheaterMapProps {
  activeConflict?: string | null;
  geointAnomalies?: GeointAnomaly[];
  sigintAircraft?: SigintAircraft[];
  sigintShips?: SigintShip[];
}

export function TheaterMap({
  activeConflict = null,
  geointAnomalies = [],
  sigintAircraft = [],
  sigintShips = [],
}: TheaterMapProps) {
  /* ---- layer visibility (useReducer instead of 6× useState) ------ */
  const [layers, dispatchLayers] = useReducer(layerReducer, INITIAL_LAYERS);
  const toggleLayer = useCallback(
    (layer: keyof LayerVisibility) => dispatchLayers({ type: "TOGGLE", layer }),
    [],
  );

  /* ---- core UI state --------------------------------------------- */
  const [selectedEvent, setSelectedEvent] = useState<TheaterEvent | null>(null);
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const [zoom, setZoom] = useState(4);
  const [center, setCenter] = useState<[number, number]>([53, 32]);

  /* ---- async data + error states --------------------------------- */
  const [theaterEvents, setTheaterEvents] = useState<TheaterEvent[]>([]);
  const [theaterLoading, setTheaterLoading] = useState(false);
  const [theaterError, setTheaterError] = useState<string | null>(null);

  const [heatmapEvents, setHeatmapEvents] = useState<ConflictEventForHeatmap[]>([]);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [heatmapError, setHeatmapError] = useState<string | null>(null);

  /* ---- derived: logarithmic marker scale ------------------------- */
  const s = markerScale(zoom);

  /* ---- stable tooltip callbacks for memo children ---------------- */
  const handleTooltipShow = useCallback(
    (content: string, color: string, e: React.MouseEvent) => {
      setTooltip({ content, color, x: e.clientX, y: e.clientY });
    },
    [],
  );
  const handleTooltipHide = useCallback(() => setTooltip(null), []);
  const handleEventSelect = useCallback((evt: TheaterEvent) => {
    setSelectedEvent(evt);
    setTooltip(null);
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

  const eventLegendItems = useMemo(() => {
    if (theaterLoading || theaterEvents.length === 0) return [];
    return (Object.entries(THEATER_EVENT_STYLE) as [string, { label: string; fill: string }][])
      .map(([key, { label, fill }]) => ({
        key,
        label,
        fill,
        count: theaterEvents.filter((e) => e.event_type === key).length,
      }))
      .filter((item) => item.count > 0);
  }, [theaterEvents, theaterLoading]);

  /* ---- render ---------------------------------------------------- */
  return (
    <div className="absolute inset-0">
      <ComposableMap
        projectionConfig={{ rotate: [-10, 0, 0], scale: 160 }}
        projection="geoNaturalEarth1"
        className="w-full h-full"
        style={{ width: "100%", height: "100%" }}
      >
        <defs>
          <filter id="theater-glow-geoint" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feFlood floodColor="#ff4400" floodOpacity="0.7" result="color" />
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
          onMoveEnd={({ coordinates, zoom: z }) => {
            setCenter(coordinates);
            setZoom(z);
          }}
          minZoom={2}
          maxZoom={8}
        >
          <TheaterGeographies />

          {layers.samRings &&
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

          {layers.airRoutes &&
            AIR_ROUTES.map((route) => (
              <Line
                key={route.id}
                coordinates={route.coordinates}
                stroke="hsl(210 80% 55% / 0.7)"
                strokeWidth={0.6}
                fill="none"
                strokeDasharray="4 2"
              />
            ))}

          {layers.seaLanes &&
            SEA_LANES.map((lane) => (
              <Line
                key={lane.id}
                coordinates={lane.coordinates}
                stroke="hsl(160 70% 45% / 0.7)"
                strokeWidth={0.6}
                fill="none"
              />
            ))}

          {layers.heatmap && !heatmapLoading && (
            <HeatmapLayer events={heatmapEvents} s={s} />
          )}

          {!theaterLoading && (
            <TheaterEventsLayer
              events={theaterEvents}
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
              />
              <SigintShipsLayer
                ships={sigintShips}
                s={s}
                onTooltipShow={handleTooltipShow}
                onTooltipHide={handleTooltipHide}
              />
            </>
          )}
        </ZoomableGroup>
      </ComposableMap>

      {/* HTML tooltip portal — single instance for all layers */}
      <MapTooltip tooltip={tooltip} />

      {/* Zoom controls */}
      <div className="absolute top-2 right-2 flex flex-col gap-1">
        <button
          type="button"
          onClick={() => setZoom((z) => Math.min(z * 1.5, 8))}
          className="w-6 h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          aria-label="Zoom in"
        >
          <Plus size={12} />
        </button>
        <button
          type="button"
          onClick={() => setZoom((z) => Math.max(z / 1.5, 2))}
          className="w-6 h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          aria-label="Zoom out"
        >
          <Minus size={12} />
        </button>
      </div>

      {/* Escalation detail panel */}
      {selectedEvent && (
        <div className="absolute bottom-24 right-2 max-w-xs w-[260px] rounded-lg border border-border bg-card/95 backdrop-blur-sm shadow-lg p-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex flex-col">
              <span className="font-mono text-[10px] text-muted-foreground tracking-wider uppercase">
                Escalation detail
              </span>
              <span className="text-xs font-semibold">
                {THEATER_EVENT_STYLE[selectedEvent.event_type]?.label ?? selectedEvent.event_type}
              </span>
            </div>
            <button
              type="button"
              aria-label="Close escalation details"
              className="h-6 w-6 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60"
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
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
            <span>Source</span>
            <span className="text-right">
              {selectedEvent.source ?? "Mixed (FIRMS/ACLED/UCDP)"}
            </span>
            <span>Confidence</span>
            <span className="text-right">
              {selectedEvent.confidence ?? "n/a"}
            </span>
            <span>Location</span>
            <span className="text-right">
              {selectedEvent.lon.toFixed(1)}E · {selectedEvent.lat.toFixed(1)}N
            </span>
          </div>
          <p className="text-[9px] text-muted-foreground">
            Unified escalation event from GEOINT/SIGINT feeds. Use key findings and news panel for full narrative.
          </p>
        </div>
      )}

      {/* Layer toggle bar */}
      <div className="absolute bottom-12 left-2 flex items-center gap-3 flex-wrap">
        <button
          type="button"
          onClick={() => toggleLayer("geoint")}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <span style={{ color: layers.geoint ? "#ff4400" : undefined }}>△</span>
          GEOINT
        </button>
        <button
          type="button"
          onClick={() => toggleLayer("sigint")}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <span style={{ color: layers.sigint ? "#60a5fa" : undefined }}>✈</span>
          <span style={{ color: layers.sigint ? "#34d399" : undefined }}>⚓</span>
          SIGINT
        </button>
        <button
          type="button"
          onClick={() => toggleLayer("heatmap")}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
          title="Conflict intensity from ACLED"
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
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
          title="SAM engagement zones"
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
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
          title="Main air corridors"
        >
          <span style={{ color: layers.airRoutes ? "hsl(210 80% 55%)" : undefined }}>✈</span>
          AIR
        </button>
        <button
          type="button"
          onClick={() => toggleLayer("seaLanes")}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
          title="Sea lanes"
        >
          <span style={{ color: layers.seaLanes ? "hsl(160 70% 45%)" : undefined }}>⚓</span>
          SEA
        </button>
        {eventLegendItems.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            {eventLegendItems.map(({ key, label, fill }) => (
              <div key={key} className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: fill }} title={label} />
                <span className="text-[10px] font-mono text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Live feed indicator */}
      {(geointAnomalies.length > 0 || sigintAircraft.length > 0 || sigintShips.length > 0) && (
        <div className="absolute top-2 left-2 flex items-center gap-2 bg-card/80 border border-border/50 rounded px-2 py-1">
          <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          <span className="text-[10px] font-mono text-muted-foreground">
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
      {theaterLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/50 pointer-events-none">
          <span className="text-xs font-mono text-muted-foreground animate-pulse">Loading theater…</span>
        </div>
      )}
    </div>
  );
}

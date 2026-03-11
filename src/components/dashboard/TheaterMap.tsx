import { useEffect, useState, useCallback, memo } from "react";
import { Plus, Minus } from "lucide-react";
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
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [animPhase, setAnimPhase] = useState(0);
  const [zoom, setZoom] = useState(4);
  const [center, setCenter] = useState<[number, number]>([53, 32]);
  const [showGeoint, setShowGeoint] = useState(true);
  const [showSigint, setShowSigint] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [heatmapEvents, setHeatmapEvents] = useState<ConflictEventForHeatmap[]>([]);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [showSamRings, setShowSamRings] = useState(false);
  const [showAirRoutes, setShowAirRoutes] = useState(false);
  const [showSeaLanes, setShowSeaLanes] = useState(false);
  const [theaterEvents, setTheaterEvents] = useState<TheaterEvent[]>([]);
  const [theaterLoading, setTheaterLoading] = useState(false);

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
    if (!showHeatmap || !activeConflict) {
      setHeatmapEvents([]);
      return;
    }
    setHeatmapLoading(true);
    getConflictEvents(activeConflict, 200)
      .then((data) => {
        if (data?.events) setHeatmapEvents(data.events);
        else setHeatmapEvents([]);
      })
      .catch(() => setHeatmapEvents([]))
      .finally(() => setHeatmapLoading(false));
  }, [showHeatmap, activeConflict]);

  useEffect(() => {
    if (!activeConflict) {
      setTheaterEvents([]);
      return;
    }
    setTheaterLoading(true);
    getTheaterEvents(activeConflict, 400)
      .then((data) => {
        if (data?.events) setTheaterEvents(data.events);
        else setTheaterEvents([]);
      })
      .catch(() => setTheaterEvents([]))
      .finally(() => setTheaterLoading(false));
  }, [activeConflict]);

  useEffect(() => {
    const interval = setInterval(() => setAnimPhase((p) => (p + 1) % 60), 50);
    return () => clearInterval(interval);
  }, []);

  const s = 1 / zoom;

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

          {showSamRings &&
            SAM_RINGS.map((sam) => {
              const coords = circlePoints(sam.center[0], sam.center[1], sam.radius_km);
              return (
                <Line
                  key={sam.id}
                  coordinates={coords}
                  stroke="hsl(var(--destructive) / 0.6)"
                  strokeWidth={0.5}
                  fill="none"
                  strokeDasharray="2 2"
                />
              );
            })}

          {showAirRoutes &&
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

          {showSeaLanes &&
            SEA_LANES.map((lane) => (
              <Line
                key={lane.id}
                coordinates={lane.coordinates}
                stroke="hsl(160 70% 45% / 0.7)"
                strokeWidth={0.6}
                fill="none"
              />
            ))}

          {showHeatmap &&
            !heatmapLoading &&
            heatmapEvents.map((evt, i) => {
              const r = (2 + evt.intensity * 5) * s;
              const opacity = 0.15 + evt.intensity * 0.35;
              return (
                <Marker key={`heat-${i}`} coordinates={[evt.lon, evt.lat]}>
                  <g pointerEvents="none">
                    <circle
                      r={r}
                      fill="#dc2626"
                      fillOpacity={opacity}
                      stroke="rgba(220,38,38,0.4)"
                      strokeWidth={0.2 * s}
                    />
                  </g>
                </Marker>
              );
            })}

          {!theaterLoading &&
            theaterEvents.map((evt, i) => {
              const style = THEATER_EVENT_STYLE[evt.event_type] ?? THEATER_EVENT_STYLE.other;
              const r = 3 * s;
              const pulseScale = 1 + 0.2 * Math.sin((animPhase + i * 5) * 0.15);
              const isHovered = hoveredId === `theater-${i}`;
              return (
                <Marker key={`theater-${i}`} coordinates={[evt.lon, evt.lat]}>
                  <g
                    className="cursor-pointer"
                    onMouseEnter={() => setHoveredId(`theater-${i}`)}
                    onMouseLeave={() => setHoveredId(null)}
                  >
                    <circle
                      r={r * 2 * pulseScale}
                      fill="none"
                      stroke={style.stroke}
                      strokeWidth={0.3 * s}
                      opacity={0.35}
                    />
                    {evt.event_type === "airstrike" && (
                      <polygon
                        points={`0,${-r * 1.2} ${r * 0.7},${r * 0.4} ${r * 0.5},${r} ${0},${r * 0.6} ${-r * 0.5},${r} ${-r * 1.2},${r * 0.4}`}
                        fill={style.fill}
                        stroke={style.stroke}
                        strokeWidth={0.25 * s}
                      />
                    )}
                    {evt.event_type === "missile" && (
                      <polygon
                        points={`0,${-r * 1.4} ${-r * 0.45},${r * 1} ${r * 0.45},${r * 1}`}
                        fill={style.fill}
                        stroke={style.stroke}
                        strokeWidth={0.25 * s}
                      />
                    )}
                    {evt.event_type === "drone" && (
                      <polygon
                        points={`0,${-r} ${r},${0} ${0},${r} ${-r},${0}`}
                        fill={style.fill}
                        stroke={style.stroke}
                        strokeWidth={0.25 * s}
                      />
                    )}
                    {(evt.event_type === "explosion" || evt.event_type === "fire" || evt.event_type === "other") && (
                      <circle r={r * 0.7} fill={style.fill} stroke={style.stroke} strokeWidth={0.25 * s} />
                    )}
                    {evt.event_type === "naval" && (
                      <g fill={style.fill} stroke={style.stroke} strokeWidth={0.3 * s}>
                        <circle r={r * 0.5} fill="none" />
                        <line x1={0} y1={-r * 0.5} x2={0} y2={r * 0.8} />
                        <path d={`M ${-r * 0.6} ${r * 0.5} L ${r * 0.6} ${r * 0.5}`} fill="none" />
                      </g>
                    )}
                    {isHovered && evt.label && (
                      <g>
                        <rect
                          x={6 * s}
                          y={-12 * s}
                          width={Math.min(evt.label.length * 5 + 12, 120) * s}
                          height={18 * s}
                          rx={2 * s}
                          fill="hsl(var(--card))"
                          stroke={style.stroke}
                          strokeWidth={0.5 * s}
                          opacity={0.95}
                        />
                        <text
                          x={10 * s}
                          y={-1 * s}
                          fill="hsl(var(--foreground))"
                          fontSize={8 * s}
                          fontFamily="JetBrains Mono, monospace"
                        >
                          {evt.label.length > 22 ? evt.label.slice(0, 22) + "…" : evt.label}
                        </text>
                      </g>
                    )}
                  </g>
                </Marker>
              );
            })}

          {showGeoint &&
            geointAnomalies.map((anomaly, i) => {
              const intensity = anomaly.frp > 1000 ? 1 : anomaly.frp > 100 ? 0.7 : 0.4;
              const r = Math.min(3 + anomaly.frp / 200, 8) * s;
              const pulseScale = 1 + 0.3 * Math.sin((animPhase + i * 7) * 0.2);
              return (
                <Marker key={`geoint-${i}`} coordinates={[anomaly.longitude, anomaly.latitude]}>
                  <g
                    filter="url(#theater-glow-geoint)"
                    className="cursor-pointer"
                    onMouseEnter={() => setHoveredId(`geoint-${i}`)}
                    onMouseLeave={() => setHoveredId(null)}
                  >
                    <circle
                      r={r * 2.5 * pulseScale}
                      fill="none"
                      stroke="#ff4400"
                      strokeWidth={0.4 * s}
                      opacity={0.25 / pulseScale}
                    />
                    <polygon
                      points={`0,${-r * 1.8} ${r * 1.2},${r * 0.9} ${-r * 1.2},${r * 0.9}`}
                      fill={`rgba(255, ${Math.floor(68 + (1 - intensity) * 100)}, 0, ${0.7 + intensity * 0.3})`}
                      stroke="#ff2200"
                      strokeWidth={0.3 * s}
                    />
                    {hoveredId === `geoint-${i}` && (
                      <g>
                        <rect
                          x={6 * s}
                          y={-14 * s}
                          width={110 * s}
                          height={22 * s}
                          rx={3 * s}
                          fill="hsl(var(--card))"
                          stroke="#ff4400"
                          strokeWidth={0.5 * s}
                          opacity={0.95}
                        />
                        <text
                          x={10 * s}
                          y={-1 * s}
                          fill="hsl(var(--foreground))"
                          fontSize={9 * s}
                          fontFamily="JetBrains Mono, monospace"
                        >
                          {anomaly.classification} · FRP {Math.round(anomaly.frp)} MW
                        </text>
                      </g>
                    )}
                  </g>
                </Marker>
              );
            })}

          {showSigint &&
            sigintAircraft.map((ac, i) => (
              <Marker key={`ac-${i}`} coordinates={[ac.lon, ac.lat]}>
                <g
                  className="cursor-pointer"
                  onMouseEnter={() => setHoveredId(`ac-${i}`)}
                  onMouseLeave={() => setHoveredId(null)}
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
                  {hoveredId === `ac-${i}` && (
                    <g>
                      <rect
                        x={8 * s}
                        y={-14 * s}
                        width={(ac.flight.length * 7 + 16) * s}
                        height={20 * s}
                        rx={3 * s}
                        fill="hsl(var(--card))"
                        stroke="#60a5fa"
                        strokeWidth={0.5 * s}
                        opacity={0.95}
                      />
                      <text
                        x={12 * s}
                        y={-1 * s}
                        fill="hsl(var(--foreground))"
                        fontSize={9 * s}
                        fontFamily="JetBrains Mono, monospace"
                      >
                        {ac.flight}
                      </text>
                    </g>
                  )}
                </g>
              </Marker>
            ))}

          {showSigint &&
            sigintShips.map((ship, i) => (
              <Marker key={`ship-${i}`} coordinates={[ship.lon, ship.lat]}>
                <g
                  className="cursor-pointer"
                  onMouseEnter={() => setHoveredId(`ship-${i}`)}
                  onMouseLeave={() => setHoveredId(null)}
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
                  {hoveredId === `ship-${i}` && (
                    <g>
                      <rect
                        x={8 * s}
                        y={-14 * s}
                        width={(ship.name.length * 7 + 16) * s}
                        height={20 * s}
                        rx={3 * s}
                        fill="hsl(var(--card))"
                        stroke="#34d399"
                        strokeWidth={0.5 * s}
                        opacity={0.95}
                      />
                      <text
                        x={12 * s}
                        y={-1 * s}
                        fill="hsl(var(--foreground))"
                        fontSize={9 * s}
                        fontFamily="JetBrains Mono, monospace"
                      >
                        {ship.name}
                      </text>
                    </g>
                  )}
                </g>
              </Marker>
            ))}
        </ZoomableGroup>
      </ComposableMap>

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

      <div className="absolute bottom-12 left-2 flex items-center gap-3 flex-wrap">
        <button
          type="button"
          onClick={() => setShowGeoint((v) => !v)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <span style={{ color: showGeoint ? "#ff4400" : undefined }}>△</span>
          GEOINT
        </button>
        <button
          type="button"
          onClick={() => setShowSigint((v) => !v)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <span style={{ color: showSigint ? "#60a5fa" : undefined }}>✈</span>
          <span style={{ color: showSigint ? "#34d399" : undefined }}>⚓</span>
          SIGINT
        </button>
        <button
          type="button"
          onClick={() => setShowHeatmap((v) => !v)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
          title="Conflict intensity from ACLED"
        >
          <span
            className={`w-2.5 h-2.5 rounded-full border ${showHeatmap ? "bg-red-500/60 border-red-500" : "bg-muted/40 border-border"}`}
          />
          HEATMAP
          {heatmapLoading && showHeatmap && <span className="animate-pulse">…</span>}
        </button>
        <button
          type="button"
          onClick={() => setShowSamRings((v) => !v)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
          title="SAM engagement zones"
        >
          <span
            className={`w-2.5 h-2.5 rounded-full border ${showSamRings ? "border-destructive" : "border-border"}`}
            style={showSamRings ? { borderColor: "hsl(var(--destructive))", background: "hsl(var(--destructive) / 0.2)" } : {}}
          />
          SAM
        </button>
        <button
          type="button"
          onClick={() => setShowAirRoutes((v) => !v)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
          title="Main air corridors"
        >
          <span style={{ color: showAirRoutes ? "hsl(210 80% 55%)" : undefined }}>✈</span>
          AIR
        </button>
        <button
          type="button"
          onClick={() => setShowSeaLanes((v) => !v)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
          title="Sea lanes"
        >
          <span style={{ color: showSeaLanes ? "hsl(160 70% 45%)" : undefined }}>⚓</span>
          SEA
        </button>
        {!theaterLoading && theaterEvents.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            {(Object.entries(THEATER_EVENT_STYLE) as [string, { label: string; fill: string }][]).map(([key, { label, fill }]) => {
              const count = theaterEvents.filter((e) => e.event_type === key).length;
              if (count === 0) return null;
              return (
                <div key={key} className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: fill }} title={label} />
                  <span className="text-[10px] font-mono text-muted-foreground">{label}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

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

      {theaterLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/50 pointer-events-none">
          <span className="text-xs font-mono text-muted-foreground animate-pulse">Loading theater…</span>
        </div>
      )}
    </div>
  );
}

import { useEffect, useState, useCallback, memo } from "react";
import { Plus, Minus, RotateCcw } from "lucide-react";
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from "react-simple-maps";
import { conflicts, severityColor } from "./conflictData";
import { ConnectionLines } from "./ConnectionLines";
import { conflictLinks } from "./conflictData";

const GEO_URL = "https://unpkg.com/world-atlas@2.0.2/countries-110m.json";

// ── Types ──────────────────────────────────────────────────────────────────
export interface GeointAnomaly {
  latitude: number;
  longitude: number;
  frp: number; // Fire Radiative Power
  confidence: string; // "high" | "nominal" | "low"
  classification: string;
}

export interface SigintAircraft {
  flight: string;
  lat: number;
  lon: number;
  category?: string;
}

export interface SigintShip {
  name: string;
  lat: number;
  lon: number;
  type?: string;
}

interface ConflictMapProps {
  geointAnomalies?: GeointAnomaly[];
  sigintAircraft?: SigintAircraft[];
  sigintShips?: SigintShip[];
  activeConflict?: string | null; // e.g. "US-Iran" → auto-zoom
}

// ── Conflict region centers for auto-zoom ─────────────────────────────────
const CONFLICT_CENTERS: Record<string, { center: [number, number]; zoom: number }> = {
  "us-iran": { center: [53, 28], zoom: 3.5 },
  ukraine: { center: [32, 48], zoom: 4 },
  "israel-palestine": { center: [35, 31], zoom: 5 },
  "taiwan-strait": { center: [120, 24], zoom: 4 },
  sudan: { center: [30, 15], zoom: 3.5 },
  yemen: { center: [46, 15], zoom: 4 },
  myanmar: { center: [96, 20], zoom: 4 },
  sahel: { center: [2, 15], zoom: 3 },
  korea: { center: [127, 37], zoom: 4.5 },
  syria: { center: [38, 35], zoom: 5 },
  drc: { center: [24, -3], zoom: 3.5 },
  ethiopia: { center: [40, 9], zoom: 4 },
};

// Fuzzy match: "US-Iran" → "us-iran"
function matchConflict(name: string): string | null {
  if (!name) return null;
  const normalized = name
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "");
  for (const key of Object.keys(CONFLICT_CENTERS)) {
    if (normalized.includes(key) || key.split("-").every((part) => normalized.includes(part))) {
      return key;
    }
  }
  return null;
}

// ── Static world map ───────────────────────────────────────────────────────
const WorldGeographies = memo(() => (
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
WorldGeographies.displayName = "WorldGeographies";

// ── Main component ─────────────────────────────────────────────────────────
export function ConflictMap({
  geointAnomalies = [],
  sigintAircraft = [],
  sigintShips = [],
  activeConflict = null,
}: ConflictMapProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [animPhase, setAnimPhase] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [center, setCenter] = useState<[number, number]>([10, 20]);
  const [showLinks, setShowLinks] = useState(true);
  const [hiddenLinks, setHiddenLinks] = useState<Set<string>>(new Set());
  const [showGeoint, setShowGeoint] = useState(true);
  const [showSigint, setShowSigint] = useState(true);

  // Pulse animation
  useEffect(() => {
    const interval = setInterval(() => setAnimPhase((p) => (p + 1) % 60), 50);
    return () => clearInterval(interval);
  }, []);

  // Auto-zoom when activeConflict changes
  useEffect(() => {
    if (!activeConflict) return;
    const key = matchConflict(activeConflict);
    if (key && CONFLICT_CENTERS[key]) {
      const { center: c, zoom: z } = CONFLICT_CENTERS[key];
      setCenter(c);
      setZoom(z);
    }
  }, [activeConflict]);

  const toggleLink = useCallback((id: string) => {
    setHiddenLinks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const allHidden = showLinks ? hiddenLinks : new Set(conflictLinks.map((l) => l.id));

  const s = 1 / zoom; // inverse scale for markers

  return (
    <div className="absolute inset-0">
      <ComposableMap
        projectionConfig={{ rotate: [-10, 0, 0], scale: 160 }}
        projection="geoNaturalEarth1"
        className="w-full h-full"
        style={{ width: "100%", height: "100%" }}
      >
        <defs>
          {(["high", "medium", "low"] as const).map((sv) => (
            <filter key={sv} id={`glow-${sv}`} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feFlood floodColor={severityColor[sv]} floodOpacity="0.6" result="color" />
              <feComposite in="color" in2="blur" operator="in" result="shadow" />
              <feMerge>
                <feMergeNode in="shadow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          ))}
          {/* GEOINT glow – orange/red */}
          <filter id="glow-geoint" x="-50%" y="-50%" width="200%" height="200%">
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
          minZoom={1}
          maxZoom={8}
        >
          <WorldGeographies />

          <ConnectionLines hiddenLinks={allHidden} onToggleLink={toggleLink} animPhase={animPhase} zoom={zoom} />

          {/* ── GEOINT Thermal Anomalies ── */}
          {showGeoint &&
            geointAnomalies.map((anomaly, i) => {
              const intensity = anomaly.frp > 1000 ? 1 : anomaly.frp > 100 ? 0.7 : 0.4;
              const r = Math.min(3 + anomaly.frp / 200, 8) * s;
              const pulseScale = 1 + 0.3 * Math.sin((animPhase + i * 7) * 0.2);
              return (
                <Marker key={`geoint-${i}`} coordinates={[anomaly.longitude, anomaly.latitude]}>
                  <g
                    filter="url(#glow-geoint)"
                    className="cursor-pointer"
                    onMouseEnter={() => setHoveredId(`geoint-${i}`)}
                    onMouseLeave={() => setHoveredId(null)}
                  >
                    {/* Outer pulse ring */}
                    <circle
                      r={r * 2.5 * pulseScale}
                      fill="none"
                      stroke="#ff4400"
                      strokeWidth={0.4 * s}
                      opacity={0.25 / pulseScale}
                    />
                    {/* Triangle marker */}
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

          {/* ── SIGINT Aircraft ── */}
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

          {/* ── SIGINT Ships ── */}
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

          {/* ── Conflict Markers ── */}
          {conflicts.map((c) => {
            const color = severityColor[c.severity];
            const pulseScale = 1 + 0.4 * Math.sin((animPhase + parseInt(c.id, 36)) * 0.15);
            const isHovered = hoveredId === c.id;
            return (
              <Marker
                key={c.id}
                coordinates={c.coordinates}
                onMouseEnter={() => setHoveredId(c.id)}
                onMouseLeave={() => setHoveredId(null)}
              >
                <g className="cursor-pointer" filter={`url(#glow-${c.severity})`} transform={`scale(${s})`}>
                  <circle r={8 * pulseScale} fill="none" stroke={color} strokeWidth={0.5} opacity={0.4 / pulseScale} />
                  <circle r={14 * pulseScale} fill="none" stroke={color} strokeWidth={0.3} opacity={0.2 / pulseScale} />
                  <circle r={isHovered ? 5 : 3.5} fill={color} opacity={0.9} />
                  {isHovered && (
                    <g>
                      <rect
                        x={8}
                        y={-12}
                        width={c.label.length * 7.5 + 16}
                        height={20}
                        rx={3}
                        fill="hsl(var(--card))"
                        stroke={color}
                        strokeWidth={0.5}
                        opacity={0.95}
                      />
                      <text
                        x={16}
                        y={2}
                        fill="hsl(var(--foreground))"
                        fontSize={10}
                        fontFamily="JetBrains Mono, monospace"
                      >
                        {c.label}
                      </text>
                    </g>
                  )}
                </g>
              </Marker>
            );
          })}
        </ZoomableGroup>
      </ComposableMap>

      {/* ── Zoom controls ── */}
      <div className="absolute top-3 right-3 flex flex-col gap-1">
        <button
          onClick={() => setZoom((z) => Math.min(z * 1.5, 8))}
          className="w-7 h-7 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
        >
          <Plus size={14} />
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(z / 1.5, 1))}
          className="w-7 h-7 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
        >
          <Minus size={14} />
        </button>
        <button
          onClick={() => {
            setZoom(1);
            setCenter([10, 20]);
          }}
          className="w-7 h-7 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
        >
          <RotateCcw size={12} />
        </button>
      </div>

      {/* ── Legend ── */}
      <div className="absolute bottom-4 left-4 flex items-center gap-4 flex-wrap">
        {/* Severity */}
        {(
          [
            ["high", "HIGH"],
            ["medium", "MED"],
            ["low", "LOW"],
          ] as const
        ).map(([sv, label]) => (
          <div key={sv} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: severityColor[sv] }} />
            <span className="text-[10px] font-mono text-muted-foreground">{label}</span>
          </div>
        ))}

        {/* GEOINT toggle */}
        <button
          onClick={() => setShowGeoint((v) => !v)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <span style={{ color: showGeoint ? "#ff4400" : undefined }}>△</span>
          GEOINT
        </button>

        {/* SIGINT toggle */}
        <button
          onClick={() => setShowSigint((v) => !v)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <span style={{ color: showSigint ? "#60a5fa" : undefined }}>✈</span>
          <span style={{ color: showSigint ? "#34d399" : undefined }}>⚓</span>
          SIGINT
        </button>

        {/* Links toggle */}
        <button
          onClick={() => setShowLinks((v) => !v)}
          className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <div
            className={`w-2.5 h-0.5 ${showLinks ? "bg-primary" : "bg-muted-foreground/40"}`}
            style={{ borderTop: "1px dashed" }}
          />
          {showLinks ? "LINKS ON" : "LINKS OFF"}
        </button>

        {hiddenLinks.size > 0 && showLinks && (
          <button
            onClick={() => setHiddenLinks(new Set())}
            className="text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
          >
            RESET
          </button>
        )}
      </div>

      {/* ── Live indicator ── */}
      {(geointAnomalies.length > 0 || sigintAircraft.length > 0 || sigintShips.length > 0) && (
        <div className="absolute top-3 left-3 flex items-center gap-2 bg-card/80 border border-border/50 rounded px-2 py-1">
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
    </div>
  );
}

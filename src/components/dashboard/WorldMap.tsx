import { useState, useCallback, useEffect, memo } from "react";
import { Plus, Minus, RotateCcw } from "lucide-react";
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup,
} from "react-simple-maps";
import { conflicts, severityColor } from "./conflictData";
import { conflictLinks } from "./conflictData";
import { ConnectionLines } from "./ConnectionLines";
import {
  GEO_URL,
  DEFAULT_WORLD_CENTER,
  DEFAULT_WORLD_ZOOM,
} from "./mapConfig";

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

interface WorldMapProps {
  /** Current conflict for optional highlight on world map */
  activeConflict?: string | null;
}

export function WorldMap({ activeConflict = null }: WorldMapProps) {
  const [zoom, setZoom] = useState(DEFAULT_WORLD_ZOOM);
  const [center, setCenter] = useState<[number, number]>(DEFAULT_WORLD_CENTER);
  const [showLinks, setShowLinks] = useState(true);
  const [hiddenLinks, setHiddenLinks] = useState<Set<string>>(new Set());
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [animPhase, setAnimPhase] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setAnimPhase((p) => (p + 1) % 60), 50);
    return () => clearInterval(interval);
  }, []);

  const toggleLink = useCallback((id: string) => {
    setHiddenLinks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const allHidden = showLinks
    ? hiddenLinks
    : new Set(conflictLinks.map((l) => l.id));
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
          {(["high", "medium", "low"] as const).map((sv) => (
            <filter
              key={sv}
              id={`world-glow-${sv}`}
              x="-50%"
              y="-50%"
              width="200%"
              height="200%"
            >
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feFlood floodColor={severityColor[sv]} floodOpacity="0.6" result="color" />
              <feComposite in="color" in2="blur" operator="in" result="shadow" />
              <feMerge>
                <feMergeNode in="shadow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          ))}
        </defs>

        <ZoomableGroup
          zoom={zoom}
          center={center}
          onMoveEnd={({ coordinates, zoom: z }) => {
            setCenter(coordinates);
            setZoom(z);
          }}
          minZoom={1}
          maxZoom={4}
        >
          <WorldGeographies />
          <ConnectionLines
            hiddenLinks={allHidden}
            onToggleLink={toggleLink}
            animPhase={animPhase}
            zoom={zoom}
          />

          {conflicts.map((c) => {
            const color = severityColor[c.severity];
            const pulseScale =
              1 + 0.4 * Math.sin((animPhase + parseInt(c.id, 36)) * 0.15);
            const isHovered = hoveredId === c.id;
            return (
              <Marker
                key={c.id}
                coordinates={c.coordinates}
                onMouseEnter={() => setHoveredId(c.id)}
                onMouseLeave={() => setHoveredId(null)}
              >
                <g
                  className="cursor-pointer"
                  filter={`url(#world-glow-${c.severity})`}
                  transform={`scale(${s})`}
                >
                  <circle
                    r={8 * pulseScale}
                    fill="none"
                    stroke={color}
                    strokeWidth={0.5}
                    opacity={0.4 / pulseScale}
                  />
                  <circle
                    r={14 * pulseScale}
                    fill="none"
                    stroke={color}
                    strokeWidth={0.3}
                    opacity={0.2 / pulseScale}
                  />
                  <circle
                    r={isHovered ? 5 : 3.5}
                    fill={color}
                    opacity={0.9}
                  />
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

      <div className="absolute top-2 right-2 flex flex-col gap-1">
        <button
          type="button"
          onClick={() => setZoom((z) => Math.min(z * 1.5, 4))}
          className="w-6 h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          aria-label="Zoom in"
        >
          <Plus size={12} />
        </button>
        <button
          type="button"
          onClick={() => setZoom((z) => Math.max(z / 1.5, 1))}
          className="w-6 h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          aria-label="Zoom out"
        >
          <Minus size={12} />
        </button>
        <button
          type="button"
          onClick={() => {
            setZoom(DEFAULT_WORLD_ZOOM);
            setCenter(DEFAULT_WORLD_CENTER);
          }}
          className="w-6 h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          aria-label="Reset to world view"
        >
          <RotateCcw size={11} />
        </button>
      </div>

      <div className="absolute bottom-2 left-2 flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => setShowLinks((v) => !v)}
          className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <div
            className={`w-2.5 h-0.5 ${showLinks ? "bg-primary" : "bg-muted-foreground/40"}`}
            style={{ borderTop: "1px dashed" }}
          />
          {showLinks ? "LINKS ON" : "LINKS OFF"}
        </button>
        {hiddenLinks.size > 0 && showLinks && (
          <button
            type="button"
            onClick={() => setHiddenLinks(new Set())}
            className="text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors"
          >
            RESET
          </button>
        )}
      </div>
    </div>
  );
}

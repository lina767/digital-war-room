import { useEffect, useState, memo } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup,
} from "react-simple-maps";

const GEO_URL = "https://unpkg.com/world-atlas@2.0.2/countries-110m.json";

interface ConflictMarker {
  id: string;
  label: string;
  coordinates: [number, number]; // [longitude, latitude]
  severity: "high" | "medium" | "low";
}

const conflicts: ConflictMarker[] = [
  { id: "us-iran", label: "US–Iran", coordinates: [53, 32], severity: "high" },
  { id: "ukraine", label: "Ukraine", coordinates: [31, 49], severity: "high" },
  { id: "sudan", label: "Sudan", coordinates: [30, 15], severity: "high" },
  { id: "myanmar", label: "Myanmar", coordinates: [96, 20], severity: "medium" },
  { id: "taiwan-strait", label: "Taiwan Strait", coordinates: [120, 24], severity: "medium" },
  { id: "sahel", label: "Sahel Region", coordinates: [2, 15], severity: "medium" },
  { id: "ethiopia", label: "Ethiopia", coordinates: [40, 9], severity: "low" },
  { id: "syria", label: "Syria", coordinates: [38, 35], severity: "medium" },
  { id: "yemen", label: "Yemen", coordinates: [48, 15], severity: "high" },
  { id: "drc", label: "DRC", coordinates: [24, -3], severity: "low" },
  { id: "korea", label: "Korean Peninsula", coordinates: [127, 38], severity: "low" },
  { id: "israel-palestine", label: "Israel–Palestine", coordinates: [35, 31.5], severity: "high" },
];

const severityColor = {
  high: "hsl(var(--threat))",
  medium: "hsl(var(--warning))",
  low: "hsl(var(--primary))",
};

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

export function ConflictMap() {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [animPhase, setAnimPhase] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [center, setCenter] = useState<[number, number]>([10, 20]);

  useEffect(() => {
    const interval = setInterval(() => setAnimPhase((p) => (p + 1) % 60), 50);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="absolute inset-0">
      <ComposableMap
        projectionConfig={{
          rotate: [-10, 0, 0],
          scale: 160,
        }}
        projection="geoNaturalEarth1"
        className="w-full h-full"
        style={{ width: "100%", height: "100%" }}
      >
        <defs>
          {(["high", "medium", "low"] as const).map((s) => (
            <filter key={s} id={`glow-${s}`} x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feFlood floodColor={severityColor[s]} floodOpacity="0.6" result="color" />
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
          maxZoom={8}
        >
          <WorldGeographies />

          {conflicts.map((c) => {
            const color = severityColor[c.severity];
            const pulseScale = 1 + 0.4 * Math.sin((animPhase + parseInt(c.id, 36)) * 0.15);
            const isHovered = hoveredId === c.id;
            const s = 1 / zoom;

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
                      <rect x={8} y={-12} width={c.label.length * 7.5 + 16} height={20} rx={3} fill="hsl(var(--card))" stroke={color} strokeWidth={0.5} opacity={0.95} />
                      <text x={16} y={2} fill="hsl(var(--foreground))" fontSize={10} fontFamily="JetBrains Mono, monospace">{c.label}</text>
                    </g>
                  )}
                </g>
              </Marker>
            );
          })}
        </ZoomableGroup>
      </ComposableMap>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 flex gap-4">
        {([["high", "HIGH"], ["medium", "MED"], ["low", "LOW"]] as const).map(([s, label]) => (
          <div key={s} className="flex items-center gap-1.5">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: severityColor[s] }}
            />
            <span className="text-[10px] font-mono text-muted-foreground">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

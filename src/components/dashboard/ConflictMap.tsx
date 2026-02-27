import { useEffect, useState } from "react";

interface ConflictMarker {
  id: string;
  label: string;
  x: number;
  y: number;
  severity: "high" | "medium" | "low";
}

const conflicts: ConflictMarker[] = [
  { id: "us-iran", label: "US–Iran", x: 620, y: 230, severity: "high" },
  { id: "ukraine", label: "Ukraine", x: 570, y: 160, severity: "high" },
  { id: "sudan", label: "Sudan", x: 560, y: 280, severity: "high" },
  { id: "myanmar", label: "Myanmar", x: 730, y: 260, severity: "medium" },
  { id: "taiwan-strait", label: "Taiwan Strait", x: 770, y: 230, severity: "medium" },
  { id: "sahel", label: "Sahel Region", x: 480, y: 280, severity: "medium" },
  { id: "ethiopia", label: "Ethiopia", x: 575, y: 300, severity: "low" },
  { id: "syria", label: "Syria", x: 580, y: 210, severity: "medium" },
  { id: "yemen", label: "Yemen", x: 600, y: 260, severity: "high" },
  { id: "drc", label: "DRC", x: 545, y: 330, severity: "low" },
  { id: "korea", label: "Korean Peninsula", x: 790, y: 195, severity: "low" },
  { id: "israel-palestine", label: "Israel–Palestine", x: 575, y: 220, severity: "high" },
];

const severityColor = {
  high: "hsl(var(--threat))",
  medium: "hsl(var(--warning))",
  low: "hsl(var(--primary))",
};

export function ConflictMap() {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [animPhase, setAnimPhase] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setAnimPhase(p => (p + 1) % 60), 50);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="absolute inset-0">
      <svg viewBox="0 0 1000 500" className="w-full h-full" preserveAspectRatio="xMidYMid slice">
        <defs>
          {/* Glow filters per severity */}
          {(["high", "medium", "low"] as const).map(s => (
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

        {/* Simplified world landmasses */}
        <g opacity="0.15" fill="hsl(var(--foreground))" stroke="hsl(var(--border))" strokeWidth="0.5">
          {/* North America */}
          <path d="M120,80 L180,60 L220,80 L250,100 L260,130 L250,160 L230,180 L200,200 L180,220 L160,210 L140,180 L100,170 L80,140 L90,110 Z" />
          <path d="M160,210 L200,200 L220,220 L230,250 L210,260 L190,250 L170,230 Z" />
          {/* South America */}
          <path d="M230,280 L260,270 L290,290 L300,320 L310,350 L300,380 L280,410 L260,430 L250,420 L240,390 L230,350 L220,320 L220,290 Z" />
          {/* Europe */}
          <path d="M460,80 L500,70 L540,80 L560,100 L570,130 L560,150 L540,160 L510,170 L480,160 L460,140 L450,110 Z" />
          {/* Africa */}
          <path d="M470,200 L510,190 L550,200 L580,220 L590,260 L580,300 L570,340 L550,370 L530,390 L510,380 L490,360 L470,330 L460,290 L450,250 L460,220 Z" />
          {/* Asia */}
          <path d="M580,60 L650,50 L720,60 L780,80 L820,110 L840,150 L830,180 L800,200 L760,210 L720,200 L680,190 L640,170 L600,150 L580,120 L570,90 Z" />
          {/* Middle East */}
          <path d="M560,170 L600,160 L640,180 L650,210 L640,240 L610,260 L580,250 L560,230 L550,200 Z" />
          {/* India/SE Asia */}
          <path d="M660,200 L700,210 L730,240 L740,270 L730,300 L710,310 L690,290 L670,260 L660,230 Z" />
          {/* Australia */}
          <path d="M760,340 L820,330 L860,350 L870,380 L850,410 L810,420 L770,400 L750,370 Z" />
          {/* Russia/Northern Asia */}
          <path d="M560,60 L600,40 L700,30 L800,40 L860,60 L880,90 L860,100 L800,90 L720,70 L640,60 L580,70 Z" />
        </g>

        {/* Grid lines */}
        <g stroke="hsl(var(--border))" strokeWidth="0.3" opacity="0.3">
          {[100, 200, 300, 400].map(y => (
            <line key={`h${y}`} x1="0" y1={y} x2="1000" y2={y} strokeDasharray="4 8" />
          ))}
          {[200, 400, 600, 800].map(x => (
            <line key={`v${x}`} x1={x} y1="0" x2={x} y2="500" strokeDasharray="4 8" />
          ))}
        </g>

        {/* Conflict markers */}
        {conflicts.map((c) => {
          const color = severityColor[c.severity];
          const pulseScale = 1 + 0.4 * Math.sin((animPhase + parseInt(c.id, 36)) * 0.15);
          const isHovered = hoveredId === c.id;

          return (
            <g
              key={c.id}
              onMouseEnter={() => setHoveredId(c.id)}
              onMouseLeave={() => setHoveredId(null)}
              className="cursor-pointer"
              filter={`url(#glow-${c.severity})`}
            >
              {/* Pulse ring */}
              <circle
                cx={c.x}
                cy={c.y}
                r={8 * pulseScale}
                fill="none"
                stroke={color}
                strokeWidth="0.5"
                opacity={0.4 / pulseScale}
              />
              <circle
                cx={c.x}
                cy={c.y}
                r={14 * pulseScale}
                fill="none"
                stroke={color}
                strokeWidth="0.3"
                opacity={0.2 / pulseScale}
              />
              {/* Core dot */}
              <circle cx={c.x} cy={c.y} r={isHovered ? 5 : 3.5} fill={color} opacity="0.9" />

              {/* Label on hover */}
              {isHovered && (
                <g>
                  <rect
                    x={c.x + 8}
                    y={c.y - 12}
                    width={c.label.length * 7.5 + 16}
                    height={20}
                    rx="3"
                    fill="hsl(var(--card))"
                    stroke={color}
                    strokeWidth="0.5"
                    opacity="0.95"
                  />
                  <text
                    x={c.x + 16}
                    y={c.y + 2}
                    fill="hsl(var(--foreground))"
                    fontSize="10"
                    fontFamily="JetBrains Mono, monospace"
                  >
                    {c.label}
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* Legend */}
        <g transform="translate(30, 430)">
          {([["high", "HIGH"], ["medium", "MED"], ["low", "LOW"]] as const).map(([s, label], i) => (
            <g key={s} transform={`translate(${i * 70}, 0)`}>
              <circle cx="5" cy="5" r="3" fill={severityColor[s]} />
              <text x="14" y="9" fill="hsl(var(--muted-foreground))" fontSize="8" fontFamily="JetBrains Mono, monospace">{label}</text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}

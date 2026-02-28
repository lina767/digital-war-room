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

        {/* Coastline glow filter */}
        <filter id="coast-glow" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feFlood floodColor="hsl(var(--primary))" floodOpacity="0.25" result="color" />
          <feComposite in="color" in2="blur" operator="in" result="glow" />
          <feMerge>
            <feMergeNode in="glow" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        {/* Detailed Low-Poly world landmasses */}
        <g opacity="0.18" fill="hsl(var(--foreground))" stroke="hsl(var(--primary))" strokeWidth="0.4" strokeOpacity="0.35" filter="url(#coast-glow)">
          {/* Greenland */}
          <path d="M280,38 L295,32 L315,30 L330,35 L340,45 L338,58 L328,68 L312,72 L295,68 L282,58 L278,48 Z" />

          {/* North America */}
          <path d="M80,65 L95,58 L115,52 L140,48 L165,50 L185,45 L205,42 L225,48 L240,55 L252,50 L260,55 L265,65 L270,58 L280,62 L278,72 L270,80 L262,78 L255,85 L260,95 L268,100 L272,110 L270,120 L265,128 L258,135 L250,140 L242,148 L235,155 L225,162 L218,170 L210,175 L200,180 L192,188 L185,195 L175,198 L168,192 L160,188 L155,180 L148,172 L140,168 L130,165 L118,162 L108,158 L100,150 L92,142 L85,132 L80,120 L78,108 L75,95 L78,80 Z" />
          {/* Alaska */}
          <path d="M55,62 L68,55 L82,52 L90,58 L85,65 L75,68 L62,68 Z" />
          {/* Central America */}
          <path d="M175,198 L185,200 L195,205 L205,210 L215,218 L222,225 L225,232 L220,238 L212,235 L205,230 L198,225 L190,218 L182,212 L175,205 Z" />
          {/* Caribbean */}
          <path d="M225,198 L235,195 L245,198 L248,205 L242,210 L232,208 L225,202 Z" />

          {/* South America */}
          <path d="M225,245 L235,240 L248,238 L260,242 L272,248 L280,255 L288,265 L295,278 L300,290 L305,305 L308,318 L310,332 L308,345 L305,358 L300,370 L292,382 L282,392 L272,400 L262,408 L255,415 L250,422 L248,430 L252,438 L248,442 L240,438 L235,428 L232,418 L230,405 L228,392 L225,378 L222,365 L220,350 L218,335 L218,320 L220,305 L222,290 L222,275 L222,260 Z" />

          {/* Iceland */}
          <path d="M395,52 L408,48 L418,50 L425,55 L422,62 L412,65 L402,62 L395,58 Z" />

          {/* UK & Ireland */}
          <path d="M440,95 L448,88 L455,85 L460,90 L458,98 L452,105 L445,108 L438,102 Z" />
          <path d="M432,98 L438,95 L440,102 L436,105 L430,102 Z" />

          {/* Scandinavia */}
          <path d="M488,38 L495,32 L505,28 L515,30 L522,35 L525,45 L528,55 L530,65 L528,78 L522,88 L515,95 L508,98 L500,95 L495,88 L490,78 L488,65 L486,52 Z" />
          {/* Finland */}
          <path d="M530,42 L540,38 L548,42 L550,52 L548,62 L542,72 L535,78 L528,72 L528,58 L530,48 Z" />

          {/* Europe mainland */}
          <path d="M445,110 L455,105 L465,100 L478,95 L488,98 L498,102 L505,108 L510,115 L515,122 L520,130 L522,138 L520,145 L515,152 L508,158 L500,162 L492,165 L485,168 L478,165 L470,160 L465,155 L458,150 L452,148 L448,142 L445,135 L442,128 L440,120 Z" />
          {/* Iberian Peninsula */}
          <path d="M432,148 L442,142 L452,148 L455,155 L452,165 L445,172 L435,175 L428,170 L425,162 L428,155 Z" />
          {/* Italy */}
          <path d="M490,145 L495,140 L500,148 L505,158 L502,168 L498,175 L492,178 L488,172 L485,162 L488,152 Z" />
          {/* Greece/Balkans */}
          <path d="M515,148 L525,145 L532,150 L535,158 L532,168 L528,175 L522,180 L515,178 L510,170 L512,160 Z" />

          {/* Africa */}
          <path d="M450,195 L462,190 L475,188 L488,190 L500,192 L512,195 L525,198 L538,202 L548,208 L555,215 L562,225 L568,238 L572,252 L575,265 L576,278 L575,292 L572,305 L568,318 L562,330 L555,342 L548,352 L538,362 L528,370 L518,378 L508,382 L498,380 L488,375 L478,368 L470,358 L462,348 L456,335 L452,322 L448,308 L445,295 L442,280 L440,265 L440,250 L442,235 L445,220 L448,208 Z" />
          {/* Madagascar */}
          <path d="M585,345 L592,338 L598,342 L600,355 L596,368 L590,375 L584,370 L582,358 Z" />

          {/* Russia / Northern Asia */}
          <path d="M535,40 L555,35 L575,32 L598,30 L620,28 L645,28 L668,30 L690,32 L712,35 L735,38 L758,40 L780,42 L800,45 L818,48 L835,52 L848,58 L855,65 L858,75 L855,82 L848,88 L838,92 L825,95 L810,92 L795,88 L778,85 L760,82 L742,80 L722,78 L702,76 L682,75 L662,76 L642,78 L622,80 L605,82 L590,85 L575,88 L562,92 L550,95 L540,92 L532,85 L528,75 L530,62 L532,50 Z" />

          {/* Middle East */}
          <path d="M555,178 L568,175 L578,172 L590,170 L600,172 L612,175 L622,180 L630,188 L635,198 L638,208 L640,218 L638,228 L632,238 L625,245 L615,250 L605,252 L595,248 L585,242 L575,235 L568,225 L562,215 L558,205 L555,195 L554,185 Z" />
          {/* Arabian Peninsula */}
          <path d="M575,225 L588,220 L598,222 L608,228 L615,238 L618,250 L615,262 L608,270 L598,275 L588,272 L578,265 L572,255 L570,242 Z" />

          {/* India */}
          <path d="M645,195 L658,188 L672,185 L685,188 L698,195 L708,205 L715,218 L718,232 L720,248 L718,262 L712,275 L705,288 L698,298 L688,305 L678,308 L668,305 L660,295 L655,282 L650,268 L648,252 L645,238 L642,222 L642,208 Z" />
          {/* Sri Lanka */}
          <path d="M688,310 L695,308 L698,315 L695,322 L688,320 Z" />

          {/* Southeast Asia */}
          <path d="M720,205 L732,198 L745,195 L758,198 L768,205 L775,215 L778,225 L775,238 L768,248 L758,252 L748,248 L738,242 L730,232 L725,220 Z" />
          {/* Indonesia */}
          <path d="M738,285 L755,280 L772,278 L788,282 L800,288 L808,295 L802,302 L790,305 L775,308 L758,305 L745,300 L738,292 Z" />
          <path d="M810,295 L825,292 L838,298 L842,308 L835,315 L822,312 L812,305 Z" />
          {/* Philippines */}
          <path d="M790,228 L798,222 L805,225 L808,235 L805,248 L798,255 L790,252 L788,240 Z" />

          {/* China / East Asia */}
          <path d="M690,98 L710,92 L730,88 L750,90 L768,95 L785,102 L798,112 L808,125 L812,138 L810,152 L802,165 L790,175 L775,182 L758,185 L742,182 L725,178 L710,172 L698,162 L688,150 L682,138 L678,125 L680,112 Z" />

          {/* Japan */}
          <path d="M822,118 L830,112 L838,115 L842,125 L840,138 L835,148 L828,155 L822,152 L818,142 L816,130 Z" />
          <path d="M828,155 L835,152 L840,158 L838,168 L832,172 L826,168 L825,160 Z" />

          {/* Korea */}
          <path d="M800,128 L808,122 L815,128 L815,140 L810,150 L802,155 L798,148 L796,138 Z" />

          {/* Australia */}
          <path d="M755,350 L775,342 L798,335 L822,332 L845,335 L862,342 L875,352 L882,365 L885,378 L882,392 L875,405 L862,415 L845,420 L828,422 L808,418 L790,412 L775,402 L762,390 L755,375 L752,362 Z" />
          {/* New Zealand */}
          <path d="M892,398 L900,392 L908,395 L912,405 L908,418 L900,425 L892,420 L890,408 Z" />
          <path d="M885,420 L892,418 L896,425 L892,432 L885,430 Z" />

          {/* Papua New Guinea */}
          <path d="M852,305 L868,298 L882,302 L888,312 L882,320 L868,322 L855,318 Z" />
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

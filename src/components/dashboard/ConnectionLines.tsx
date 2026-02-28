import { memo, useState, useCallback } from "react";
import { Line, Marker } from "react-simple-maps";
import { conflicts, conflictLinks } from "./conflictData";

interface ConnectionLinesProps {
  hiddenLinks: Set<string>;
  onToggleLink: (id: string) => void;
  animPhase: number;
  zoom: number;
}

const coordsMap = new Map(conflicts.map((c) => [c.id, c.coordinates]));

export const ConnectionLines = memo(function ConnectionLines({
  hiddenLinks,
  onToggleLink,
  animPhase,
  zoom,
}: ConnectionLinesProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const s = 1 / zoom;

  const handleMouseEnter = useCallback((id: string) => setHoveredId(id), []);
  const handleMouseLeave = useCallback(() => setHoveredId(null), []);

  return (
    <>
      {conflictLinks
        .filter((link) => !hiddenLinks.has(link.id))
        .map((link) => {
          const from = coordsMap.get(link.from);
          const to = coordsMap.get(link.to);
          if (!from || !to) return null;

          const dashOffset = -(animPhase * 2);
          const isHovered = hoveredId === link.id;

          return (
            <Line
              key={link.id}
              from={from}
              to={to}
              stroke={isHovered ? "hsl(var(--primary) / 0.8)" : "hsl(var(--primary) / 0.4)"}
              strokeWidth={isHovered ? 1.8 : 1}
              strokeLinecap="round"
              strokeDasharray="4 4"
              strokeDashoffset={dashOffset}
              className="cursor-pointer"
              onClick={() => onToggleLink(link.id)}
              onMouseEnter={() => handleMouseEnter(link.id)}
              onMouseLeave={handleMouseLeave}
            />
          );
        })}

      {/* Tooltips rendered as Markers at midpoints */}
      {conflictLinks
        .filter((link) => !hiddenLinks.has(link.id) && hoveredId === link.id)
        .map((link) => {
          const from = coordsMap.get(link.from);
          const to = coordsMap.get(link.to);
          if (!from || !to) return null;
          const mid: [number, number] = [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2];

          return (
            <Marker key={`tip-${link.id}`} coordinates={mid}>
              <g transform={`scale(${s})`} style={{ pointerEvents: "none" }}>
                <rect
                  x={-link.label.length * 3.5 - 8}
                  y={-22}
                  width={link.label.length * 7 + 16}
                  height={18}
                  rx={3}
                  fill="hsl(var(--card))"
                  stroke="hsl(var(--primary))"
                  strokeWidth={0.5}
                  opacity={0.95}
                />
                <text
                  y={-10}
                  textAnchor="middle"
                  fill="hsl(var(--foreground))"
                  fontSize={9}
                  fontFamily="JetBrains Mono, monospace"
                >
                  {link.label}
                </text>
              </g>
            </Marker>
          );
        })}
    </>
  );
});

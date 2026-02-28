import { memo } from "react";
import { Line } from "react-simple-maps";
import { conflicts, conflictLinks, type ConflictLink } from "./conflictData";

interface ConnectionLinesProps {
  hiddenLinks: Set<string>;
  onToggleLink: (id: string) => void;
  animPhase: number;
}

const coordsMap = new Map(conflicts.map((c) => [c.id, c.coordinates]));

export const ConnectionLines = memo(function ConnectionLines({
  hiddenLinks,
  onToggleLink,
  animPhase,
}: ConnectionLinesProps) {
  return (
    <>
      {conflictLinks
        .filter((link) => !hiddenLinks.has(link.id))
        .map((link) => {
          const from = coordsMap.get(link.from);
          const to = coordsMap.get(link.to);
          if (!from || !to) return null;

          const dashOffset = -(animPhase * 2);

          return (
            <Line
              key={link.id}
              from={from}
              to={to}
              stroke="hsl(var(--primary) / 0.4)"
              strokeWidth={1}
              strokeLinecap="round"
              strokeDasharray="4 4"
              strokeDashoffset={dashOffset}
              className="cursor-pointer"
              onClick={() => onToggleLink(link.id)}
            />
          );
        })}
    </>
  );
});

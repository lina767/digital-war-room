import { useState } from "react";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { IntelPanel } from "@/components/dashboard/IntelPanel";

type TimelineFilter = "all" | "conflict" | "diplomacy" | "economy" | "tech";

const FILTER_LABELS: Record<TimelineFilter, string> = {
  all: "All",
  conflict: "Conflict",
  diplomacy: "Diplomacy",
  economy: "Economy",
  tech: "Tech",
};

function categorizeFinding(f: string): TimelineFilter {
  const lower = f.toLowerCase();
  if (lower.includes("sigint") || lower.includes("geoint") || lower.includes("strike") || lower.includes("military")) return "conflict";
  if (lower.includes("diplomat") || lower.includes("sanction") || lower.includes("cia") || lower.includes("talks")) return "diplomacy";
  if (lower.includes("oil") || lower.includes("brent") || lower.includes("market") || lower.includes("crude")) return "economy";
  if (lower.includes("techint") || lower.includes("ioda") || lower.includes("internet") || lower.includes("shodan")) return "tech";
  return "all";
}

interface EventsTimelineProps {
  data: ConflictData | null;
}

export function EventsTimeline({ data }: EventsTimelineProps) {
  const [filter, setFilter] = useState<TimelineFilter>("all");
  const findings = data?.key_findings ?? [];
  const filtered =
    filter === "all"
      ? findings
      : findings.filter((f) => categorizeFinding(f) === filter);

  return (
    <IntelPanel
      title="EVENTS TIMELINE"
      headerRight={
        <div className="flex flex-wrap gap-1">
          {(Object.keys(FILTER_LABELS) as TimelineFilter[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors ${
                filter === key
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted"
              }`}
            >
              {FILTER_LABELS[key]}
            </button>
          ))}
        </div>
      }
    >
      <ul className="divide-y divide-border/60 max-h-48 overflow-y-auto px-3 py-2">
        {filtered.length === 0 && (
          <li className="py-3 text-xs text-muted-foreground italic">
            {findings.length === 0 ? "Run analysis for events." : `No events in category "${FILTER_LABELS[filter]}".`}
          </li>
        )}
        {filtered.slice(0, 20).map((f, i) => (
          <li key={i} className="py-2 text-xs leading-relaxed flex gap-2">
            <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-primary mt-1.5" />
            <span>{f}</span>
          </li>
        ))}
      </ul>
    </IntelPanel>
  );
}

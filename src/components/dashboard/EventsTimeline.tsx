import { useState } from "react";
import type { ConflictData } from "@/types/conflict";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { DASHBOARD_PANEL_TOOLTIPS } from "@/lib/dashboardPanelCopy";
import { WhyThisMattersBlock } from "@/components/dashboard/WhyThisMattersBlock";
import { FindingConfidenceBadge, normalizeFindingConfidence } from "@/components/dashboard/FindingConfidenceBadge";

type TimelineFilter = "all" | "conflict" | "diplomacy" | "economy" | "tech";

const DEFAULT_VISIBLE = 8;
const MAX_VISIBLE = 20;

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
  embedded?: boolean;
}

export function EventsTimeline({ data, embedded = false }: EventsTimelineProps) {
  const [filter, setFilter] = useState<TimelineFilter>("all");
  const [showAll, setShowAll] = useState(false);
  const findings = data?.key_findings ?? [];
  const indexed = findings.map((f, i) => ({ f, i }));
  const filtered =
    filter === "all"
      ? indexed
      : indexed.filter(({ f }) => categorizeFinding(f) === filter);
  const visibleCount = showAll ? Math.min(filtered.length, MAX_VISIBLE) : Math.min(filtered.length, DEFAULT_VISIBLE);
  const display = filtered.slice(0, visibleCount);
  const hasMore = filtered.length > visibleCount;

  return (
    <IntelPanel
      title="EVENTS TIMELINE"
      tooltipContent={DASHBOARD_PANEL_TOOLTIPS["EVENTS TIMELINE"]}
      embedded={embedded}
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
        {display.map(({ f, i }) => (
          <li key={`${filter}-${i}-${f.slice(0, 40)}`} className="py-2 text-xs leading-relaxed">
            <div className="flex gap-2 items-start">
              <FindingConfidenceBadge level={normalizeFindingConfidence(data?.key_findings_confidence?.[i])} />
              <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-primary mt-1.5" />
              <span className="min-w-0">{f}</span>
            </div>
            {data?.key_findings_context?.[i] != null && String(data.key_findings_context[i]).trim() !== "" && (
              <div className="mt-1.5 ml-3.5 pl-1">
                <WhyThisMattersBlock text={data.key_findings_context[i]!} />
              </div>
            )}
          </li>
        ))}
      </ul>
      {hasMore && filtered.length > 0 && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="w-full px-3 py-2 text-[11px] font-mono text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors flex items-center justify-center gap-1"
        >
          Show more ({filtered.length - visibleCount} more)
        </button>
      )}
    </IntelPanel>
  );
}

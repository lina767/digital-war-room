import { useMemo } from "react";
import type { EscalationTimelinePoint } from "@/lib/api";
import type { StrikeTimeRange } from "@/features/theater-map/components/LayerControls";

const RANGE_PRESETS: { key: StrikeTimeRange; label: string }[] = [
  { key: "6h", label: "6h" },
  { key: "24h", label: "24h" },
  { key: "7d", label: "7d" },
  { key: "all", label: "All" },
];

function dotColorForScore(score: number): string {
  if (score >= 67) return "bg-threat";
  if (score >= 34) return "bg-warning";
  return "bg-primary";
}

function windowSeconds(range: StrikeTimeRange): number | null {
  if (range === "all") return null;
  const hours: Record<Exclude<StrikeTimeRange, "all">, number> = {
    "6h": 6,
    "24h": 24,
    "48h": 48,
    "7d": 7 * 24,
  };
  return hours[range] * 3600;
}

function filterPoints(points: EscalationTimelinePoint[], range: StrikeTimeRange): EscalationTimelinePoint[] {
  const ws = windowSeconds(range);
  if (ws == null) return points;
  const now = Date.now() / 1000;
  const cutoff = now - ws;
  return points.filter((p) => typeof p.at === "number" && p.at >= cutoff);
}

interface VisualEscalationTimelineProps {
  points: EscalationTimelinePoint[];
  strikeTimeRange: StrikeTimeRange;
  onStrikeTimeRangeChange: (r: StrikeTimeRange) => void;
  onPointClick?: (point: EscalationTimelinePoint) => void;
}

/**
 * Time-window presets synced with map strike layers; filtered escalation dots + horizontal track.
 */
export function VisualEscalationTimeline({
  points,
  strikeTimeRange,
  onStrikeTimeRangeChange,
  onPointClick,
}: VisualEscalationTimelineProps) {
  const filtered = useMemo(() => filterPoints(points, strikeTimeRange), [points, strikeTimeRange]);

  const trackLayout = useMemo(() => {
    if (filtered.length === 0) return { dots: [] as { leftPct: number; p: EscalationTimelinePoint }[] };
    const ats = filtered.map((p) => p.at as number).filter((a) => typeof a === "number");
    if (ats.length === 0) return { dots: [] as { leftPct: number; p: EscalationTimelinePoint }[] };
    const minT = Math.min(...ats);
    const maxT = Math.max(...ats);
    const span = Math.max(maxT - minT, 1);
    return {
      dots: filtered.map((p) => ({
        leftPct: ((p.at as number) - minT) / span,
        p,
      })),
    };
  }, [filtered]);

  const scrollToFeed = () => {
    document.getElementById("dwr-feed-section-events-timeline")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <div className="space-y-2 w-full min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] sm:text-[11px] text-muted-foreground shrink-0">Window</span>
        <div className="flex flex-wrap gap-1">
          {RANGE_PRESETS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => onStrikeTimeRangeChange(key)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono border transition-colors ${
                strikeTimeRange === key
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:bg-muted/60"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="text-[10px] text-muted-foreground font-mono ml-auto">
          {filtered.length}/{points.length} runs
        </span>
      </div>

      <div
        className="relative h-9 rounded border border-border/80 bg-muted/20 overflow-hidden"
        role="img"
        aria-label="Escalation score over selected time window"
      >
        <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
        {trackLayout.dots.map(({ leftPct, p }, i) => (
          <button
            key={`${p.at}-${i}`}
            type="button"
            title={`${p.label_with_date ?? p.label ?? ""} · score ${p.escalation_score ?? "–"}`}
            className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full ${dotColorForScore(
              p.escalation_score ?? 0,
            )} ring-2 ring-background hover:scale-125 transition-transform`}
            style={{ left: `${Math.min(100, Math.max(0, leftPct * 100))}%` }}
            onClick={() => {
              onPointClick?.(p);
              scrollToFeed();
            }}
          />
        ))}
        {filtered.length === 0 && points.length > 0 && (
          <span className="absolute inset-0 flex items-center justify-center text-[10px] text-muted-foreground font-mono px-2 text-center">
            No analysis runs in this window — choose &quot;All&quot; or a wider range.
          </span>
        )}
        {points.length === 0 && (
          <span className="absolute inset-0 flex items-center justify-center text-[10px] text-muted-foreground font-mono italic px-2 text-center">
            No timeline data yet.
          </span>
        )}
      </div>

      <div className="flex items-center gap-2 sm:gap-3 min-w-0 overflow-x-auto pb-0.5">
        {filtered.map((p, i) => (
          <div key={p.at ?? i} className="flex flex-col items-center gap-0.5 flex-shrink-0">
            <button
              type="button"
              className={`h-2 w-2 rounded-full flex-shrink-0 ${dotColorForScore(p.escalation_score ?? 0)}`}
              title={`${p.label_with_date ?? p.label ?? "–"} · ${p.escalation_score ?? "–"}`}
              onClick={() => {
                onPointClick?.(p);
                scrollToFeed();
              }}
            />
            <span className="font-mono text-[10px] text-muted-foreground whitespace-nowrap" title={p.datetime_iso ?? undefined}>
              {p.label ?? "–"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

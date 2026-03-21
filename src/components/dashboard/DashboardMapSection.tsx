import { useEffect, useState } from "react";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import type { GeointAnomaly, SigintAircraft, SigintShip } from "./mapConfig";
import { TheaterMap } from "@/components/dashboard/TheaterMap";
import { Radio, Rss } from "lucide-react";
import { getEscalationTimeline, type EscalationTimelinePoint } from "@/lib/api";

interface DashboardMapSectionProps {
  leftPanelOpen: boolean;
  setLeftPanelOpen: (open: boolean) => void;
  rightPanelOpen: boolean;
  setRightPanelOpen: (open: boolean) => void;
  /** Current conflict for map zoom and theater/heatmap data. */
  activeConflict?: string | null;
  /** Analysis data for GEOINT/SIGINT on theater map. */
  conflictData?: ConflictData | null;
}

function dotColorForScore(score: number): string {
  if (score >= 67) return "bg-threat";
  if (score >= 34) return "bg-warning";
  return "bg-primary";
}

export function DashboardMapSection({
  leftPanelOpen,
  setLeftPanelOpen,
  rightPanelOpen,
  setRightPanelOpen,
  activeConflict = null,
  conflictData = null,
}: DashboardMapSectionProps) {
  const [timelinePoints, setTimelinePoints] = useState<EscalationTimelinePoint[]>([]);

  useEffect(() => {
    if (!activeConflict) {
      setTimelinePoints([]);
      return;
    }
    let cancelled = false;
    getEscalationTimeline(activeConflict).then((data) => {
      if (!cancelled && data?.points?.length) setTimelinePoints(data.points);
      else if (!cancelled) setTimelinePoints([]);
    });
    return () => { cancelled = true; };
  }, [activeConflict]);

  const geointAnomalies = conflictData?.geoint?.anomalies ?? [];
  const sigintAircraft = conflictData?.sigint?.aircraft ?? [];
  const sigintShips = conflictData?.sigint?.ships ?? [];
  const chokepointStatuses = (conflictData?.chokepoint?.chokepoints ?? []).map(
    (cp: { name: string; status: string; disruption_risk: number }) => ({
      name: cp.name,
      status: cp.status as "OPEN" | "RESTRICTED" | "DISRUPTED" | "HOSTILE",
      disruption_risk: cp.disruption_risk,
    }),
  );

  return (
    <main className="flex-[0_1_50%] min-h-0 min-w-0 relative overflow-hidden flex flex-col" aria-label="Theater map and escalation timeline">
      <div className="absolute inset-0 grid-overlay opacity-30 pointer-events-none" />
      {/* Theater map only – full width for clearer overview */}
      <div className="flex-1 min-w-[280px] relative">
        <TheaterMap
          activeConflict={activeConflict}
          geointAnomalies={geointAnomalies as GeointAnomaly[]}
          sigintAircraft={sigintAircraft as SigintAircraft[]}
          sigintShips={sigintShips as SigintShip[]}
          chokepointStatuses={chokepointStatuses}
        />
      </div>

      {/* Mobile floating panel toggles – 44px tap targets */}
      <div className="absolute top-3 left-3 flex gap-2 lg:hidden z-10">
        <button
          type="button"
          aria-label="Toggle Agents panel"
          onClick={() => {
            setLeftPanelOpen(!leftPanelOpen);
            setRightPanelOpen(false);
          }}
          className="flex items-center justify-center gap-1.5 min-h-11 min-w-11 sm:min-w-0 sm:px-3 rounded-md border border-border bg-background/95 backdrop-blur-sm text-xs font-mono text-muted-foreground hover:text-foreground hover:bg-background active:bg-muted/50 transition-colors touch-manipulation shadow-sm"
        >
          <Radio className="h-4 w-4 flex-shrink-0" aria-hidden />
          <span className="hidden sm:inline">Agents</span>
        </button>
      </div>
      <div className="absolute top-3 right-3 flex gap-2 md:hidden z-10">
        <button
          type="button"
          aria-label="Toggle Intel Feed panel"
          onClick={() => {
            setRightPanelOpen(!rightPanelOpen);
            setLeftPanelOpen(false);
          }}
          className="flex items-center justify-center gap-1.5 min-h-11 min-w-11 sm:min-w-0 sm:px-3 rounded-md border border-border bg-background/95 backdrop-blur-sm text-xs font-mono text-muted-foreground hover:text-foreground hover:bg-background active:bg-muted/50 transition-colors touch-manipulation shadow-sm"
        >
          <Rss className="h-4 w-4 flex-shrink-0" aria-hidden />
          <span className="hidden sm:inline">Feed</span>
        </button>
      </div>

      {/* Bottom Escalation Timeline – real data: one point per analysis run, color by score */}
      <div className="flex-shrink-0 border-t border-border bg-background/95 backdrop-blur-sm p-3 sm:p-3 supports-[padding:env(safe-area-inset-bottom)]:pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <div className="flex items-center justify-between gap-2 min-w-0">
          <span className="font-mono text-[10px] sm:text-[11px] md:text-xs text-muted-foreground shrink-0">[ Escalation Timeline ]</span>
          <div className="flex items-center gap-2 sm:gap-3 md:gap-4 min-w-0 overflow-x-auto">
            {timelinePoints.length > 0 ? (
              timelinePoints.map((p, i) => (
                <div key={p.at ?? i} className="flex flex-col items-center gap-0.5 sm:gap-1 flex-shrink-0">
                  <div
                    className={`h-1.5 w-1.5 sm:h-2 sm:w-2 rounded-full flex-shrink-0 ${dotColorForScore(p.escalation_score ?? 0)}`}
                    title={`Abgeschlossen: ${p.label_with_date ?? p.label ?? "—"} · Score ${p.escalation_score ?? "—"}`}
                  />
                  <span className="font-mono text-[10px] sm:text-[11px] text-muted-foreground whitespace-nowrap" title={p.datetime_iso ?? undefined}>
                    {p.label_with_date ?? p.label ?? "—"}
                  </span>
                </div>
              ))
            ) : (
              <span className="font-mono text-[10px] sm:text-[11px] text-muted-foreground italic">
                No timeline data yet — escalation over time will appear here after more analysis runs.
              </span>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

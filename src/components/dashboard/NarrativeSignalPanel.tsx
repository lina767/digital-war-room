import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { Scale, Clock, AlertTriangle, MessageSquare } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface NarrativeSignalPanelProps {
  data: ConflictData | null;
  conflictLabel: string;
}

/** Only show for Iran (Signal Framework is configured for Iran narrative comparison). */
function isRelevant(conflictLabel: string, narrative: ConflictData["narrative"]): boolean {
  if (!narrative) return false;
  if (narrative.error === "conflict_not_supported") return false;
  const label = (conflictLabel || "").toLowerCase();
  return label.includes("iran");
}

export function NarrativeSignalPanel({ data, conflictLabel }: NarrativeSignalPanelProps) {
  const narrative = data?.narrative;
  if (!narrative || !isRelevant(conflictLabel, narrative)) return null;

  const table = narrative.source_comparison_table ?? [];
  const assessment = narrative.signal_assessment ?? {};
  const signals = narrative.signals;
  const reactionList = narrative.reaction_signals ?? signals?.reaction ?? [];
  const prob = narrative.synthesis_probability ?? 0;
  const synthesisText = narrative.synthesis_text ?? "";
  const anomalies = narrative.anomalies ?? [];
  const stateCount = narrative.state_item_count ?? 0;
  const exileCount = narrative.exile_item_count ?? 0;

  const probLabel = prob >= 0.7 ? "High consistency" : prob >= 0.5 ? "Moderate" : "Low consistency";
  const probVariant = prob >= 0.7 ? "default" : prob >= 0.5 ? "secondary" : "destructive";

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-muted/30 flex items-center justify-between gap-2">
        <h3 className="font-mono text-xs text-muted-foreground tracking-wider flex items-center gap-1.5">
          <Scale className="h-3.5 w-3.5" />
          NARRATIVE COMPARISON
        </h3>
        <span className="text-[10px] text-muted-foreground">
          State {stateCount} · Exile {exileCount}
        </span>
      </div>

      {stateCount === 0 && exileCount > 0 && (
        <p className="px-3 py-1.5 text-[10px] text-muted-foreground bg-muted/30 border-b border-border">
          State feeds (IRNA, Fars, Tasnim, Press TV) often return no items when accessed from outside Iran (geo-restriction).
        </p>
      )}

      <div className="p-3 space-y-4">
        {/* Synthesis (Bayesian-style) */}
        {(synthesisText || typeof prob === "number") && (
          <div>
            <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1.5">
              Most likely scenario
            </p>
            <div className="flex flex-wrap items-center gap-2 mb-1.5">
              <Badge variant={probVariant} className="text-[10px] font-mono">
                {probLabel} ({Math.round(prob * 100)}%)
              </Badge>
            </div>
            {synthesisText && (
              <p className="text-xs leading-relaxed text-foreground">{synthesisText}</p>
            )}
          </div>
        )}

        {/* Source comparison table */}
        {table.length > 0 && (
          <div>
            <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-2">
              Source comparison
            </p>
            <div className="overflow-x-auto -mx-1">
              <table className="w-full text-[11px] border-collapse">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-1.5 px-2 font-medium text-muted-foreground w-24">Point</th>
                    <th className="text-left py-1.5 px-2 font-medium text-muted-foreground">State (IRNA/Fars)</th>
                    <th className="text-left py-1.5 px-2 font-medium text-muted-foreground">Exile (Iran Int./Farda)</th>
                  </tr>
                </thead>
                <tbody>
                  {table.map((row, i) => {
                    const stateText = (row.state_narrative_en ?? row.state_narrative) || "—";
                    const exileText = (row.exile_narrative_en ?? row.exile_narrative) || "—";
                    return (
                      <tr key={i} className="border-b border-border/60">
                        <td className="py-1.5 px-2 align-top font-medium">{row.point}</td>
                        <td className="py-1.5 px-2 align-top text-foreground/90 max-w-[140px] sm:max-w-[200px]">
                          {stateText.slice(0, 200)}
                          {stateText.length > 200 ? "…" : ""}
                        </td>
                        <td className="py-1.5 px-2 align-top text-foreground/90 max-w-[140px] sm:max-w-[200px]">
                          {exileText.slice(0, 200)}
                          {exileText.length > 200 ? "…" : ""}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Signal assessment */}
        {(assessment.latency || assessment.credibility_gaps) && (
          <div className="space-y-2">
            <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
              Signal assessment
            </p>
            {assessment.latency && (
              <div className="flex gap-2 text-xs">
                <Clock className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0 mt-0.5" />
                <span><strong className="text-muted-foreground">Latency:</strong> {assessment.latency}</span>
              </div>
            )}
            {assessment.credibility_gaps && (
              <div className="flex gap-2 text-xs">
                <MessageSquare className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0 mt-0.5" />
                <span><strong className="text-muted-foreground">Credibility:</strong> {assessment.credibility_gaps.slice(0, 280)}{assessment.credibility_gaps.length > 280 ? "…" : ""}</span>
              </div>
            )}
          </div>
        )}

        {/* Four signals (compact) */}
        {(signals?.lexical?.interpretation || reactionList.length > 0) && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
              Signals
            </p>
            {signals?.lexical?.interpretation && (
              <p className="text-[11px] text-foreground/90 leading-snug">{signals.lexical.interpretation}</p>
            )}
            {reactionList.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {reactionList.slice(0, 3).map((r, i) => (
                  <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-destructive/15 text-destructive/90">
                    {r.slice(0, 60)}{r.length > 60 ? "…" : ""}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Anomalies */}
        {anomalies.length > 0 && (
          <div>
            <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1.5 flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              Anomalies
            </p>
            <ul className="space-y-1">
              {anomalies.map((a, i) => (
                <li key={i} className="text-xs text-muted-foreground flex gap-1.5">
                  <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-amber-500/80 mt-1.5" />
                  {a}
                </li>
              ))}
            </ul>
          </div>
        )}

        {narrative.fetched_at && (
          <p className="text-[10px] text-muted-foreground pt-1 border-t border-border/60">
            Data: {new Date(narrative.fetched_at).toISOString().slice(0, 19).replace("T", " ")} UTC
          </p>
        )}
      </div>
    </div>
  );
}

import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { Scale, Building2, Radio } from "lucide-react";
import { DASHBOARD_PANEL_TOOLTIPS } from "@/lib/dashboardPanelCopy";

interface SignalFrameworkPanelProps {
  data: ConflictData | null;
  /** Only show panel when this conflict is selected (e.g. Iran has narrative comparison). */
  activeConflict?: string | null;
  embedded?: boolean;
}

export function SignalFrameworkPanel({ data, activeConflict, embedded = false }: SignalFrameworkPanelProps) {
  const narrative = data?.narrative;
  const table = narrative?.source_comparison_table ?? [];
  const synthesisText = narrative?.synthesis_text ?? "";
  const probability = narrative?.synthesis_probability;
  const assessment = narrative?.signal_assessment ?? {};
  const stateCount = narrative?.state_item_count ?? 0;
  const exileCount = narrative?.exile_item_count ?? 0;
  const hasData = table.length > 0 || synthesisText || (stateCount > 0 && exileCount > 0);

  return (
    <IntelPanel
      title="SIGNAL FRAMEWORK"
      icon={<Scale className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />}
      tooltipContent={DASHBOARD_PANEL_TOOLTIPS["SIGNAL FRAMEWORK"]}
      embedded={embedded}
    >
      {!hasData && (
        <p className="text-xs text-muted-foreground italic">
          State vs. exile/independent media comparison. Run analysis for Iran to see the narrative comparison.
        </p>
      )}

      {synthesisText && (
        <div>
          <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">Synthesis</p>
          <p className="text-sm leading-relaxed">{synthesisText}</p>
          {typeof probability === "number" && (
            <p className="text-[11px] text-muted-foreground mt-1.5">
              Consistency: {probability >= 0.7 ? "High" : probability >= 0.4 ? "Medium" : "Low"} ({Math.round(probability * 100)}%)
            </p>
          )}
        </div>
      )}

      {(assessment.latency || assessment.credibility_gaps) && (
        <div className="space-y-1">
          {assessment.latency && (
            <p className="text-xs">
              <span className="text-muted-foreground">Latency:</span> {assessment.latency}
            </p>
          )}
          {assessment.credibility_gaps && (
            <p className="text-xs">
              <span className="text-muted-foreground">Credibility gaps:</span> {assessment.credibility_gaps}
            </p>
          )}
        </div>
      )}

      {table.length > 0 && (
        <div>
          <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-2">State vs. Exile</p>
          <div className="space-y-3">
            {table.map((row, i) => {
              const point = row.point ?? `Point ${i + 1}`;
              const stateText = (row.state_narrative_en ?? row.state_narrative) || "–";
              const exileText = (row.exile_narrative_en ?? row.exile_narrative) || "–";
              return (
                <div key={i} className="rounded border border-border bg-muted/20 p-2.5 space-y-2">
                  <p className="text-[11px] font-medium text-foreground">{point}</p>
                  <div className="grid gap-2 text-xs">
                    <div className="flex gap-2">
                      <span className="flex-shrink-0 flex items-center gap-1 text-muted-foreground" title="State / official">
                        <Building2 className="h-3 w-3" />
                        State
                      </span>
                      <p className="leading-relaxed text-foreground/90 min-w-0">{stateText.slice(0, 280)}{stateText.length > 280 ? "…" : ""}</p>
                    </div>
                    <div className="flex gap-2">
                      <span className="flex-shrink-0 flex items-center gap-1 text-muted-foreground" title="Exile / independent">
                        <Radio className="h-3 w-3" />
                        Exile
                      </span>
                      <p className="leading-relaxed text-foreground/90 min-w-0">{exileText.slice(0, 280)}{exileText.length > 280 ? "…" : ""}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {(stateCount > 0 || exileCount > 0) && table.length === 0 && (
        <p className="text-[11px] text-muted-foreground">
          State sources: {stateCount} · Exile/independent: {exileCount}
        </p>
      )}
    </IntelPanel>
  );
}

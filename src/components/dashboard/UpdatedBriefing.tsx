import type { ConflictData } from "@/types/conflict";
import { FindingConfidenceBadge, normalizeFindingConfidence } from "@/components/dashboard/FindingConfidenceBadge";
import { RootCauseSuggestions } from "@/components/dashboard/RootCauseSuggestions";
import { NarrativeBody } from "@/components/dashboard/NarrativeBody";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { TextSkeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { formatTimeAgo } from "@/lib/utils";
import { DASHBOARD_PANEL_TOOLTIPS } from "@/lib/dashboardPanelCopy";
import { Play } from "lucide-react";

interface UpdatedBriefingProps {
  data: ConflictData | null;
  conflictLabel: string;
  lastUpdated: Date | null;
  /** True while initial fetch of cached analysis is in progress (improves perceived load time). */
  isLoading?: boolean;
  /** True while an explicit analysis run is in progress. */
  isRunning?: boolean;
  /** Optional error message from analysis trigger/polling. */
  analysisError?: string | null;
  /** Trigger a new analysis run from the UI. */
  onRunAnalysis?: () => void | Promise<unknown>;
  /** When true, render only content (no panel title). Use when already wrapped in a CollapsiblePanel with the same title. */
  embedded?: boolean;
}

function UpdatedBriefingContent({
  data,
  conflictLabel,
  isLoading,
  isRunning,
  analysisError,
  onRunAnalysis,
}: Pick<UpdatedBriefingProps, "data" | "conflictLabel" | "isLoading" | "isRunning" | "analysisError" | "onRunAnalysis">) {
  const summary = data?.summary ?? null;
  const narrativeStory = data?.narrative_story ?? null;
  const scenarios = data?.scenarios ?? [];
  const keyFindings = data?.key_findings ?? [];
  const rootCauses = data?.root_cause_suggestions ?? [];
  const hasContent =
    summary || narrativeStory || scenarios.length > 0 || keyFindings.length > 0 || rootCauses.length > 0;

  return (
    <>
      {isLoading && !hasContent && <TextSkeleton lines={3} className="text-xs" />}
        {!hasContent && !isLoading && (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground italic">Run analysis for {conflictLabel} to see the briefing.</p>
            {analysisError && (
              <p className="text-xs text-destructive">{analysisError}</p>
            )}
            {onRunAnalysis && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 text-[11px] gap-1.5"
                onClick={() => void onRunAnalysis()}
                disabled={Boolean(isRunning)}
              >
                <Play className="h-3.5 w-3.5" aria-hidden />
                {isRunning ? "Running..." : "Run analysis"}
              </Button>
            )}
          </div>
        )}
        {summary && (
          <div className="mb-3">
            <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">Recap</p>
            <p className="text-sm leading-relaxed text-pretty">{summary}</p>
          </div>
        )}
        <RootCauseSuggestions items={rootCauses} />
        {narrativeStory && (
          <div className="mb-3">
            <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">
              Cross-stream narrative
            </p>
            <p className="text-[10px] text-muted-foreground/90 mb-2 leading-snug">
              How FININT, SIGINT, GEOINT, and related streams reinforce or qualify each other – read after the recap.
            </p>
            <NarrativeBody text={narrativeStory} />
          </div>
        )}
        {data != null && (
          <div>
            <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-2">Things to Watch</p>
            {scenarios.length > 0 ? (
              <ol className="space-y-2 list-decimal list-inside">
                {scenarios.slice(0, 5).map((s, i) => (
                  <li key={i} className="text-xs leading-relaxed">
                    <span className="font-medium">{s.description}</span>
                    {typeof s.probability === "number" && (
                      <span className="ml-1 text-muted-foreground">({Math.round(s.probability * 100)}%)</span>
                    )}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-xs text-muted-foreground italic">No scenarios on watch for this period.</p>
            )}
          </div>
        )}
        {hasContent && !summary && scenarios.length === 0 && keyFindings.length > 0 && (
          <div>
            <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-2">Key findings</p>
            <ul className="space-y-2">
              {keyFindings.slice(0, 6).map((f, i) => (
                <li key={i} className="text-xs leading-relaxed flex gap-2 items-start">
                  <FindingConfidenceBadge level={normalizeFindingConfidence(data?.key_findings_confidence?.[i])} />
                  <span className="min-w-0">• {f}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
    </>
  );
}

export function UpdatedBriefing({
  data,
  conflictLabel,
  lastUpdated,
  isLoading,
  isRunning,
  analysisError,
  onRunAnalysis,
  embedded,
}: UpdatedBriefingProps) {
  const content = (
    <UpdatedBriefingContent
      data={data}
      conflictLabel={conflictLabel}
      isLoading={isLoading}
      isRunning={isRunning}
      analysisError={analysisError}
      onRunAnalysis={onRunAnalysis}
    />
  );

  if (embedded) {
    return content;
  }

  return (
    <IntelPanel
      title="UPDATED BRIEFING"
      headerRight={<span className="text-[11px] text-muted-foreground">{formatTimeAgo(lastUpdated)}</span>}
      tooltipContent={DASHBOARD_PANEL_TOOLTIPS["UPDATED BRIEFING"]}
    >
      {content}
    </IntelPanel>
  );
}

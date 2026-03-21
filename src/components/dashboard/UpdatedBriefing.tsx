import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { FindingConfidenceBadge, normalizeFindingConfidence } from "@/components/dashboard/FindingConfidenceBadge";
import { NarrativeBody } from "@/components/dashboard/NarrativeBody";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { TextSkeleton } from "@/components/ui/skeleton";
import { formatTimeAgo } from "@/lib/utils";
import { DASHBOARD_PANEL_TOOLTIPS } from "@/lib/dashboardPanelCopy";

interface UpdatedBriefingProps {
  data: ConflictData | null;
  conflictLabel: string;
  lastUpdated: Date | null;
  /** True while initial fetch of cached analysis is in progress (improves perceived load time). */
  isLoading?: boolean;
  /** When true, render only content (no panel title). Use when already wrapped in a CollapsiblePanel with the same title. */
  embedded?: boolean;
}

function UpdatedBriefingContent({
  data,
  conflictLabel,
  isLoading,
}: Pick<UpdatedBriefingProps, "data" | "conflictLabel" | "isLoading">) {
  const summary = data?.summary ?? null;
  const narrativeStory = data?.narrative_story ?? null;
  const scenarios = data?.scenarios ?? [];
  const keyFindings = data?.key_findings ?? [];
  const hasContent =
    summary || narrativeStory || scenarios.length > 0 || keyFindings.length > 0;

  return (
    <>
      {isLoading && !hasContent && <TextSkeleton lines={3} className="text-xs" />}
        {!hasContent && !isLoading && (
          <p className="text-xs text-muted-foreground italic">Run analysis for {conflictLabel} to see the briefing.</p>
        )}
        {summary && (
          <div className="mb-3">
            <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">Recap</p>
            <p className="text-sm leading-relaxed text-pretty">{summary}</p>
          </div>
        )}
        {narrativeStory && (
          <div className="mb-3">
            <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">
              Cross-stream narrative
            </p>
            <p className="text-[10px] text-muted-foreground/90 mb-2 leading-snug">
              How FININT, SIGINT, GEOINT, and related streams reinforce or qualify each other — read after the recap.
            </p>
            <NarrativeBody text={narrativeStory} />
          </div>
        )}
        {scenarios.length > 0 && (
          <div>
            <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-2">Things to Watch</p>
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

export function UpdatedBriefing({ data, conflictLabel, lastUpdated, isLoading, embedded }: UpdatedBriefingProps) {
  const content = (
    <UpdatedBriefingContent data={data} conflictLabel={conflictLabel} isLoading={isLoading} />
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

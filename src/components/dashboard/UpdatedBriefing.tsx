import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { IntelPanel } from "@/components/dashboard/IntelPanel";

interface UpdatedBriefingProps {
  data: ConflictData | null;
  conflictLabel: string;
  lastUpdated: Date | null;
  /** True while initial fetch of cached analysis is in progress (improves perceived load time). */
  isLoading?: boolean;
}

function formatTimeAgo(date: Date | null): string {
  if (!date) return "—";
  const sec = Math.floor((Date.now() - date.getTime()) / 1000);
  if (sec < 60) return "Just now";
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

export function UpdatedBriefing({ data, conflictLabel, lastUpdated, isLoading }: UpdatedBriefingProps) {
  const summary = data?.summary ?? null;
  const scenarios = data?.scenarios ?? [];
  const keyFindings = data?.key_findings ?? [];
  const hasContent = summary || scenarios.length > 0 || keyFindings.length > 0;

  return (
    <IntelPanel
      title="UPDATED BRIEFING"
      headerRight={<span className="text-[11px] text-muted-foreground">{formatTimeAgo(lastUpdated)}</span>}
    >
      {isLoading && !hasContent && (
          <p className="text-xs text-muted-foreground italic animate-pulse">Loading analysis…</p>
        )}
        {!hasContent && !isLoading && (
          <p className="text-xs text-muted-foreground italic">Run analysis for {conflictLabel} to see the briefing.</p>
        )}
        {summary && (
          <div>
            <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">Recap</p>
            <p className="text-sm leading-relaxed">{summary}</p>
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
            <ul className="space-y-1.5">
              {keyFindings.slice(0, 6).map((f, i) => (
                <li key={i} className="text-xs leading-relaxed">• {f}</li>
              ))}
            </ul>
          </div>
        )}
    </IntelPanel>
  );
}

import { ChevronDown, ChevronUp } from "lucide-react";
import { AgentBadge } from "@/features/daily-briefing/components/AgentBadge";
import type { Finding } from "@/features/daily-briefing/types/briefing.types";
import { confidenceClass } from "@/features/daily-briefing/utils/confidenceLabel";
import { formatTimeAgo } from "@/lib/utils";

interface FindingCardProps {
  finding: Finding;
  expanded: boolean;
  onToggle: (id: string) => void;
}

export function FindingCard({ finding, expanded, onToggle }: FindingCardProps) {
  return (
    <article className="briefing-card p-3 transition-colors">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <AgentBadge agent={finding.agent} />
          <p className="text-xs italic text-[var(--text-secondary)]">{finding.type}</p>
        </div>
        <button
          className="inline-flex items-center gap-1 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          onClick={() => onToggle(finding.id)}
          type="button"
        >
          Details {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
      </div>
      <h3 className="mb-1 text-sm font-semibold">{finding.title}</h3>
      <p className="text-sm leading-relaxed text-[var(--text-primary)]">{finding.body}</p>
      {finding.operationalImplication ? (
        <p className="mt-2 rounded border border-[var(--border-subtle)] bg-[var(--bg-elevated)]/30 px-2 py-1 text-xs leading-relaxed text-[var(--text-secondary)]">
          <span className="briefing-mono text-[10px] uppercase tracking-wide text-[var(--text-tertiary)]">Operational implication: </span>
          {finding.operationalImplication}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px]">
        <span className={confidenceClass(finding.confidence)}>Confidence: {finding.confidence}</span>
        <span className="text-[var(--text-secondary)]">Source Tier: {finding.sourceTier}</span>
        <span className="text-[var(--text-secondary)]">{formatTimeAgo(finding.timestamp)}</span>
      </div>
      {expanded && (
        <div className="mt-2 border-t border-[var(--border-subtle)] pt-2 text-xs text-[var(--text-secondary)]">
          <p>Raw data preview available for analyst inspection.</p>
          {finding.sourceUrls && finding.sourceUrls.length > 0 && (
            <ul className="mt-1 list-disc pl-4">
              {finding.sourceUrls.map((url) => (
                <li key={url}>
                  <a href={url} target="_blank" rel="noreferrer" className="text-[var(--text-accent)] hover:underline">
                    {url}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}

import { ChevronDown, ChevronUp } from "lucide-react";
import { AGENTS } from "@/features/daily-briefing/constants/agents";
import { AgentBadge } from "@/features/daily-briefing/components/AgentBadge";
import type { AgentDataBlock, AgentId } from "@/features/daily-briefing/types/briefing.types";

interface AgentSectionProps {
  agentId: AgentId;
  block: AgentDataBlock;
  expanded: boolean;
  onToggle: (id: AgentId) => void;
}

export function AgentSection({ agentId, block, expanded, onToggle }: AgentSectionProps) {
  return (
    <section id={`agent-${agentId.toLowerCase()}`} className="briefing-card p-3">
      <button type="button" className="flex w-full items-center justify-between gap-2" onClick={() => onToggle(agentId)}>
        <div className="flex items-center gap-2">
          <AgentBadge agent={agentId} />
          <span className="text-sm">{AGENTS[agentId].fullName}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <span className="briefing-mono">{block.status.score != null ? `${Math.round(block.status.score)}/100` : "–"}</span>
          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </div>
      </button>
      {expanded && (
        <div className="mt-3 space-y-2 text-xs">
          <p className="text-[var(--text-secondary)]">{AGENTS[agentId].description}</p>
          <div className="rounded border border-[var(--border-subtle)] p-2">
            <p className="briefing-mono text-[11px] text-[var(--text-secondary)]">MODEL / PROCESSING</p>
            <p>
              {block.metadata.model} | {block.metadata.tokensUsed} tokens | {block.metadata.latencyMs}ms
            </p>
          </div>
          <div className="rounded border border-[var(--border-subtle)] p-2">
            <p className="briefing-mono text-[11px] text-[var(--text-secondary)]">RAW DATA PREVIEW</p>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-[11px] text-[var(--text-secondary)]">
              {JSON.stringify(block.rawData, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </section>
  );
}

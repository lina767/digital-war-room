import { AGENT_ORDER, AGENTS } from "@/features/daily-briefing/constants/agents";
import type { AgentDataBlock } from "@/features/daily-briefing/types/briefing.types";
import { formatTimeAgo } from "@/lib/utils";

interface AgentStatusPanelProps {
  agents: Record<string, AgentDataBlock>;
}

function dotClass(status: string): string {
  if (status === "success") return "bg-emerald-400";
  if (status === "running") return "bg-amber-400";
  if (status === "error" || status === "timeout") return "bg-rose-400";
  return "bg-slate-500";
}

export function AgentStatusPanel({ agents }: AgentStatusPanelProps) {
  return (
    <section className="briefing-card p-3">
      <h3 className="briefing-mono mb-2 text-xs tracking-wider text-[var(--text-secondary)]">AGENT STATUS</h3>
      <div className="space-y-1.5">
        {AGENT_ORDER.map((agentId) => {
          const row = agents[agentId];
          const score = row?.status.score;
          return (
            <div key={agentId} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${dotClass(row?.status.status)}`} />
                <span className="briefing-mono">{AGENTS[agentId].label}</span>
              </div>
              <div className="flex items-center gap-3 text-[var(--text-secondary)]">
                <span className="briefing-mono">{typeof score === "number" ? `${Math.round(score)}/100` : "—"}</span>
                <span>{formatTimeAgo(row?.status.lastUpdated ?? null)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

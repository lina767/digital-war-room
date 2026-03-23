import { AGENTS } from "@/features/daily-briefing/constants/agents";
import { AgentBadge } from "@/features/daily-briefing/components/AgentBadge";
import type { AgentId, ThreatLevel } from "@/features/daily-briefing/types/briefing.types";
import { threatLevelColor } from "@/features/daily-briefing/utils/threatLevelColor";

interface BLUFSectionProps {
  summary: string;
  contributingAgents: AgentId[];
  threatLevel: ThreatLevel;
}

export function BLUFSection({ summary, contributingAgents, threatLevel }: BLUFSectionProps) {
  const firstSentenceEnd = summary.indexOf(". ");
  const lead = firstSentenceEnd > 0 ? summary.slice(0, firstSentenceEnd + 1) : summary;
  const rest = firstSentenceEnd > 0 ? summary.slice(firstSentenceEnd + 1).trim() : "";

  return (
    <section className="briefing-card mb-4 p-4" style={{ borderLeft: `4px solid ${threatLevelColor(threatLevel)}` }}>
      <p className="briefing-mono mb-2 text-[11px] uppercase tracking-wider text-[var(--text-secondary)]">BLUF</p>
      <p className="text-[17px] leading-relaxed">
        <strong>{lead}</strong> {rest}
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {contributingAgents.map((agent) => (
          <span key={`${agent}-${AGENTS[agent].label}`}>
            <AgentBadge agent={agent} />
          </span>
        ))}
      </div>
    </section>
  );
}

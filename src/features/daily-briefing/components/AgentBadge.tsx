import { AGENTS } from "@/features/daily-briefing/constants/agents";
import type { AgentId } from "@/features/daily-briefing/types/briefing.types";

interface AgentBadgeProps {
  agent: AgentId;
}

export function AgentBadge({ agent }: AgentBadgeProps) {
  return (
    <span
      className="briefing-mono inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase"
      style={{ backgroundColor: AGENTS[agent].color, color: "#fff" }}
    >
      {AGENTS[agent].label}
    </span>
  );
}

import { AGENT_ORDER } from "@/features/daily-briefing/constants/agents";
import { AgentSection } from "@/features/daily-briefing/components/AgentSection";
import type { AgentDataBlock, AgentId } from "@/features/daily-briefing/types/briefing.types";

interface AgentDeepDivesProps {
  agents: Record<string, AgentDataBlock>;
  expandedAgents: Set<AgentId>;
  onToggleAgent: (agent: AgentId) => void;
}

export function AgentDeepDives({ agents, expandedAgents, onToggleAgent }: AgentDeepDivesProps) {
  return (
    <section id="briefing-sources" className="space-y-2">
      <h2 className="briefing-display text-2xl">Agent Deep Dives</h2>
      <div className="space-y-2">
        {AGENT_ORDER.map((agentId) => (
          <AgentSection
            key={agentId}
            agentId={agentId}
            block={agents[agentId]}
            expanded={expandedAgents.has(agentId)}
            onToggle={onToggleAgent}
          />
        ))}
      </div>
    </section>
  );
}

import { AgentBadge } from "@/features/daily-briefing/components/AgentBadge";
import type { Scenario } from "@/features/daily-briefing/types/briefing.types";

interface ScenarioCardProps {
  scenario: Scenario;
}

function scenarioColor(type: Scenario["type"]) {
  if (type === "ESCALATION") return "var(--threat-critical)";
  if (type === "DE_ESCALATION") return "var(--threat-low)";
  if (type === "WILDCARD") return "var(--accent-amber)";
  return "var(--text-secondary)";
}

export function ScenarioCard({ scenario }: ScenarioCardProps) {
  return (
    <article className="briefing-card p-3">
      <p className="briefing-mono text-[11px] font-semibold" style={{ color: scenarioColor(scenario.type) }}>
        {scenario.type.replace("_", " ")}
      </p>
      <p className="briefing-mono text-3xl font-semibold">{scenario.probability}%</p>
      <p className="mt-2 text-sm">{scenario.description}</p>
      <div className="mt-2 space-y-1">
        {scenario.keyDrivers.map((driver) => (
          <div key={`${scenario.id}-${driver.agent}-${driver.reason}`} className="flex items-center gap-2">
            <AgentBadge agent={driver.agent} />
            <span className="text-xs text-[var(--text-secondary)]">{driver.reason}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 h-2 rounded bg-[var(--bg-tertiary)]">
        <div className="h-2 rounded bg-[var(--accent-blue)] transition-all duration-700" style={{ width: `${scenario.probability}%` }} />
      </div>
    </article>
  );
}

import { ScenarioCard } from "@/features/daily-briefing/components/ScenarioCard";
import type { Scenario } from "@/features/daily-briefing/types/briefing.types";

interface ScenarioAssessmentProps {
  scenarios: Scenario[];
}

export function ScenarioAssessment({ scenarios }: ScenarioAssessmentProps) {
  return (
    <section id="briefing-watch" className="space-y-2">
      <h2 className="briefing-display text-2xl">Things to Watch</h2>
      <p className="text-sm text-[var(--text-secondary)]">
        Supervisor-generated scenarios with rough probability weights — not precise forecasts.
      </p>
      {scenarios.length === 0 ? (
        <div className="briefing-card p-4 text-sm text-[var(--text-secondary)]">
          No scenarios on watch for this period.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
          {scenarios.map((scenario) => (
            <ScenarioCard key={scenario.id} scenario={scenario} />
          ))}
        </div>
      )}
    </section>
  );
}

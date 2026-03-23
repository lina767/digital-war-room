import { ScenarioCard } from "@/features/daily-briefing/components/ScenarioCard";
import type { Scenario } from "@/features/daily-briefing/types/briefing.types";

interface ScenarioAssessmentProps {
  scenarios: Scenario[];
}

export function ScenarioAssessment({ scenarios }: ScenarioAssessmentProps) {
  return (
    <section id="briefing-watch" className="space-y-2">
      <h2 className="briefing-display text-2xl">Scenario Assessment</h2>
      <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
        {scenarios.map((scenario) => (
          <ScenarioCard key={scenario.id} scenario={scenario} />
        ))}
      </div>
    </section>
  );
}

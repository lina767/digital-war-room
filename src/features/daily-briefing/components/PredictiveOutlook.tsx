import { AgentBadge } from "@/features/daily-briefing/components/AgentBadge";
import type { DailyBriefingData } from "@/features/daily-briefing/types/briefing.types";

interface PredictiveOutlookProps {
  outlook: DailyBriefingData["predictiveOutlook"];
}

export function PredictiveOutlook({ outlook }: PredictiveOutlookProps) {
  return (
    <section id="briefing-predictive" className="briefing-card p-3">
      <h2 className="briefing-display mb-2 text-2xl">Predictive Outlook</h2>
      <p className="text-sm">
        Trajectory: <span className="briefing-mono">{outlook.trajectory}</span>
      </p>
      <div className="mt-2 space-y-2">
        {outlook.signals.map((signal) => (
          <div key={`${signal.agent}-${signal.label}`} className="rounded border border-[var(--border-subtle)] p-2">
            <div className="mb-1 flex items-center justify-between">
              <AgentBadge agent={signal.agent} />
              <span className="briefing-mono text-xs">{signal.weight}/100</span>
            </div>
            <p className="text-xs text-[var(--text-secondary)]">{signal.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

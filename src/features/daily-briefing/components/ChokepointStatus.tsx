import type { ChokepointStatus as ChokepointStatusType } from "@/features/daily-briefing/types/briefing.types";

interface ChokepointStatusProps {
  chokepoints: ChokepointStatusType[];
}

function statusColor(status: ChokepointStatusType["status"]) {
  if (status === "HOSTILE") return "text-rose-300";
  if (status === "RESTRICTED") return "text-amber-300";
  return "text-emerald-300";
}

export function ChokepointStatus({ chokepoints }: ChokepointStatusProps) {
  return (
    <section className="briefing-card p-3">
      <h3 className="briefing-mono mb-2 text-xs tracking-wider text-[var(--text-secondary)]">CHOKEPOINTS</h3>
      <div className="space-y-2">
        {chokepoints.map((point) => (
          <div key={point.name}>
            <div className="flex items-center justify-between text-xs">
              <span>{point.name}</span>
              <span className={`briefing-mono ${statusColor(point.status)}`}>{point.status}</span>
            </div>
            <div className="mt-1 h-2 rounded bg-[var(--bg-tertiary)]">
              <div className="h-2 rounded bg-[var(--accent-amber)]" style={{ width: `${point.disruptionScore}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

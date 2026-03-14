import { IntelPanel } from "@/components/dashboard/IntelPanel";
import type { ConflictData, EscalationForecast, PredictiveBlock } from "@/hooks/useConflictWebSocket";

function levelBadgeClass(level: string | undefined): string {
  switch (level) {
    case "CRITICAL":
      return "bg-destructive text-destructive-foreground";
    case "HIGH":
      return "bg-orange-500/90 text-black";
    case "MEDIUM":
      return "bg-yellow-400/80 text-black";
    case "LOW":
    default:
      return "bg-emerald-500/80 text-black";
  }
}

function formatRange(range?: { min: number; max: number }): string | null {
  if (!range || typeof range.min !== "number" || typeof range.max !== "number") return null;
  const lo = Math.round(range.min * 100);
  const hi = Math.round(range.max * 100);
  return `${lo}–${hi}%`;
}

function pickForecast24h(block?: PredictiveBlock): EscalationForecast | undefined {
  const list = block?.escalation ?? [];
  if (!list.length) return undefined;
  const match = list.find((f) => f.horizon === "24h");
  return match ?? list[0];
}

interface PredictivePanelProps {
  data: ConflictData | null;
}

export function PredictivePanel({ data }: PredictivePanelProps) {
  const predictive = data?.predictive;
  if (!predictive) return null;

  const baseline = predictive.baseline_escalation;
  const forecast24h = pickForecast24h(predictive);

  if (!baseline && !forecast24h) return null;

  return (
    <IntelPanel
      title="PREDICTIVE OUTLOOK"
      headerRight={forecast24h?.horizon ? <span className="text-[11px] text-muted-foreground">Next {forecast24h.horizon}</span> : undefined}
    >
      {baseline && (
        <div className="rounded-md border border-border/60 bg-background/50 px-3 py-2 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
              Baseline (Null hypothesis)
            </span>
            <span className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${levelBadgeClass(baseline.level)}`}>
              {baseline.level}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Expected escalation level without current signals.
            {baseline.range && (
              <> Baseline band: <span className="text-foreground">{formatRange(baseline.range)}</span>.</>
            )}
          </p>
        </div>
      )}

      {forecast24h && (
        <div className="rounded-md border border-border/60 bg-background/70 px-3 py-2 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
              Escalation – {forecast24h.horizon}
            </span>
            <span className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${levelBadgeClass(forecast24h.level)}`}>
              {forecast24h.level}
            </span>
          </div>
          <p className="text-[11px] text-foreground/90">
            {forecast24h.range && (
              <>
                Band: <span className="font-mono">{formatRange(forecast24h.range)}</span>.{" "}
              </>
            )}
            {baseline && (
              <span className="text-muted-foreground">
                vs baseline: <span className="font-mono uppercase">{forecast24h.vs_baseline}</span>.
              </span>
            )}
          </p>
          {forecast24h.drivers && forecast24h.drivers.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {forecast24h.drivers.slice(0, 3).map((d, i) => (
                <li key={i} className="text-[11px] text-muted-foreground flex gap-1.5">
                  <span className="mt-[3px] h-1 w-1 rounded-full bg-primary/80 flex-shrink-0" />
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <p className="text-[11px] text-muted-foreground">
        Levels and bands are coarse; they aggregate existing agent scores relative to a historical baseline, not precise probabilities.
      </p>
    </IntelPanel>
  );
}


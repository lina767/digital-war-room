import { IntelPanel } from "@/components/dashboard/IntelPanel";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { DASHBOARD_PANEL_TOOLTIPS } from "@/lib/dashboardPanelCopy";
import {
  PREDICTIVE_OUTLOOK_DISCLAIMER,
  PREDICTIVE_OUTLOOK_INTRO,
  PREDICTIVE_OUTLOOK_INTRO_SHORT,
} from "@/lib/predictiveOutlookCopy";
import type { ConflictData, EscalationForecast, PredictiveBlock } from "@/hooks/useConflictWebSocket";
import { Info } from "lucide-react";

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

function confidenceBadgeClass(confidence: string | undefined): string {
  switch (confidence) {
    case "HIGH":
      return "text-emerald-600 dark:text-emerald-400";
    case "MEDIUM":
      return "text-amber-600 dark:text-amber-400";
    case "LOW":
    default:
      return "text-muted-foreground";
  }
}

function formatRange(range?: { min: number; max: number }): string | null {
  if (!range || typeof range.min !== "number" || typeof range.max !== "number") return null;
  const lo = Math.round(range.min * 100);
  const hi = Math.round(range.max * 100);
  return `${lo}–${hi}%`;
}

/** Returns escalation forecasts in display order: 24h first, then 7d. */
function getEscalationForecasts(block?: PredictiveBlock): EscalationForecast[] {
  const list = block?.escalation ?? [];
  if (!list.length) return [];
  const order = ["24h", "7d"];
  const sorted = [...list].sort(
    (a, b) => order.indexOf(a.horizon || "") - order.indexOf(b.horizon || "")
  );
  return sorted;
}

interface PredictivePanelProps {
  data: ConflictData | null;
}

export function PredictivePanel({ data }: PredictivePanelProps) {
  const predictive = data?.predictive;
  if (!predictive) return null;

  const baseline = predictive.baseline_escalation;
  const forecasts = getEscalationForecasts(predictive);
  const primaryHorizon = forecasts[0]?.horizon;

  if (!baseline && !forecasts.length) return null;

  const headerRight = primaryHorizon ? (
    <span className="text-[11px] text-muted-foreground">
      {forecasts.length > 1
        ? forecasts.map((f) => f.horizon).join(" · ")
        : `Next ${primaryHorizon}`}
    </span>
  ) : undefined;

  return (
    <TooltipProvider delayDuration={200}>
      <IntelPanel
        title="PREDICTIVE OUTLOOK"
        headerRight={headerRight}
        tooltipContent={DASHBOARD_PANEL_TOOLTIPS["PREDICTIVE OUTLOOK"]}
      >
        <p className="text-[11px] text-muted-foreground flex items-start gap-1.5">
          <span>{PREDICTIVE_OUTLOOK_INTRO_SHORT}</span>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="shrink-0 mt-0.5 rounded p-0.5 text-muted-foreground hover:text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                aria-label="What is this?"
              >
                <Info className="h-3 w-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[280px] text-xs">
              {PREDICTIVE_OUTLOOK_INTRO}
            </TooltipContent>
          </Tooltip>
        </p>

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
              Expected escalation level without current signals (what you’d expect if there were no new signals).
              {baseline.range && (
                <> Baseline band: <span className="text-foreground">{formatRange(baseline.range)}</span> (rough probability range).</>
              )}
            </p>
            {baseline.drivers && baseline.drivers.length > 0 && (
              <ul className="mt-1 space-y-0.5">
                {baseline.drivers.map((d, i) => (
                  <li key={i} className="text-[11px] text-muted-foreground flex gap-1.5">
                    <span className="mt-[3px] h-1 w-1 rounded-full bg-muted-foreground/60 flex-shrink-0" />
                    <span>{d}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {forecasts.map((forecast) => (
          <div
            key={forecast.horizon}
            className="rounded-md border border-border/60 bg-background/70 px-3 py-2 space-y-1"
          >
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
                Escalation – {forecast.horizon}
              </span>
              <div className="flex items-center gap-1.5">
                {forecast.confidence && (
                  <span className={`text-[10px] font-mono ${confidenceBadgeClass(forecast.confidence)}`} title="Confidence">
                    {forecast.confidence}
                  </span>
                )}
                <span className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${levelBadgeClass(forecast.level)}`}>
                  {forecast.level}
                </span>
              </div>
            </div>
            <p className="text-[11px] text-foreground/90">
              {forecast.range && (
                <>
                  Band: <span className="font-mono">{formatRange(forecast.range)}</span> (rough range).{" "}
                </>
              )}
              {baseline && (
                <span className="text-muted-foreground">
                  vs baseline: <span className="font-mono uppercase">{forecast.vs_baseline}</span>.
                </span>
              )}
            </p>
            {forecast.notes && (
              <p className="text-[10px] text-muted-foreground/80 italic" title="How this level was derived">
                {forecast.notes}
              </p>
            )}
            {forecast.drivers && forecast.drivers.length > 0 && (
              <ul className="mt-1 space-y-0.5">
                {forecast.drivers.map((d, i) => (
                  <li key={i} className="text-[11px] text-muted-foreground flex gap-1.5" title="Contributing agent score">
                    <span className="mt-[3px] h-1 w-1 rounded-full bg-primary/80 flex-shrink-0" />
                    <span>{d}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}

        <p className="text-[11px] text-muted-foreground">
          {PREDICTIVE_OUTLOOK_DISCLAIMER}
        </p>
      </IntelPanel>
    </TooltipProvider>
  );
}

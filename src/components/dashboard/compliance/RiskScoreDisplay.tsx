import { RISK_LEVEL_LABELS } from "@/lib/complianceCopy";
import type { ComplianceRiskScore } from "@/hooks/useConflictWebSocket";
import { DRIVER_SECTION_MAP, RISK_LEVEL_STYLES } from "./shared";

export function RiskScoreDisplay({
  riskScore,
  onDriverClick,
}: {
  riskScore: ComplianceRiskScore;
  onDriverClick?: (sectionId: string) => void;
}) {
  const bandText = `${Math.round(riskScore.band.min * 100)}-${Math.round(riskScore.band.max * 100)}%`;
  const levelLabel = RISK_LEVEL_LABELS[riskScore.level];

  return (
    <div className="rounded-md border border-border/60 bg-background/50 px-3 py-2 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
          Compliance Risk
        </span>
        <span
          className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${RISK_LEVEL_STYLES[riskScore.level] ?? "bg-muted text-muted-foreground"}`}
          title={levelLabel}
        >
          {riskScore.level}
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg font-bold text-primary">{riskScore.numeric_score}</span>
        <span className="text-[11px] text-muted-foreground">/100 · Band: {bandText} (rough range)</span>
      </div>
      {riskScore.drivers.length > 0 && (
        <ul className="space-y-1">
          {riskScore.drivers.slice(0, 6).map((d, i) => {
            const sectionId = DRIVER_SECTION_MAP[d.factor];
            const isClickable = sectionId && onDriverClick;
            return (
              <li key={i} className="text-[11px] text-muted-foreground">
                <div className="flex gap-1.5">
                  <span className="mt-[3px] h-1 w-1 rounded-full bg-primary/80 flex-shrink-0" />
                  <div className="min-w-0">
                    {isClickable ? (
                      <button
                        type="button"
                        onClick={() => onDriverClick(sectionId)}
                        className="text-left hover:text-foreground focus:outline-none focus:ring-1 focus:ring-primary rounded"
                      >
                        <span className="font-mono text-foreground/80">{d.factor}</span>: {d.detail}
                      </button>
                    ) : (
                      <>
                        <span className="font-mono text-foreground/80">{d.factor}</span>: {d.detail}
                      </>
                    )}
                    {d.programs && (
                      <span className="ml-1 text-[11px] text-muted-foreground/70">[{d.programs}]</span>
                    )}
                    {d.note && (
                      <p className="text-[11px] text-muted-foreground/60 mt-0.5 leading-tight">{d.note}</p>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

import type { ConflictData } from "@/types/conflict";

interface CorrelationRow {
  label: string;
  severity: "high" | "medium" | "low";
}

function toRows(items: string[], fallback: string): CorrelationRow[] {
  if (!items.length) return [{ label: fallback, severity: "low" }];
  return items.slice(0, 5).map((line) => {
    const l = line.toLowerCase();
    const severity: CorrelationRow["severity"] =
      l.includes("missile") || l.includes("rocket") || l.includes("airstrike") || l.includes("artillery")
        ? "high"
        : l.includes("drone") || l.includes("alert") || l.includes("strike")
          ? "medium"
          : "low";
    return { label: line, severity };
  });
}

const severityClass: Record<CorrelationRow["severity"], string> = {
  high: "text-red-300",
  medium: "text-amber-300",
  low: "text-emerald-300",
};

interface CrossBorderCorrelationPanelProps {
  conflictData: ConflictData | null;
}

export function CrossBorderCorrelationPanel({ conflictData }: CrossBorderCorrelationPanelProps) {
  const findings = conflictData?.key_findings ?? [];
  const sigintAlerts = Array.isArray((conflictData?.sigint as { alerts?: unknown })?.alerts)
    ? (((conflictData?.sigint as { alerts?: unknown })?.alerts ?? []) as Array<{ text?: string }>)
        .map((a) => String(a?.text || "").trim())
        .filter(Boolean)
    : [];
  const northIsrael = [
    ...sigintAlerts.filter((x) => /israel|galilee|kiryat|haifa|nahariya|upper galilee|north israel/i.test(x)),
    ...findings.filter((x) => /israel|galilee|haifa|north israel/i.test(x)),
  ];
  const southLebanon = [
    ...findings.filter((x) => /south lebanon|lebanon|blue line|litani|nabatieh|tyre|dahiyeh|beirut/i.test(x)),
  ];
  const leftRows = toRows(northIsrael, "No north-Israel alert strings in current cycle.");
  const rightRows = toRows(southLebanon, "No south-Lebanon activity strings in current cycle.");

  const matchingSignals = Math.min(leftRows.length, rightRows.length);
  const correlationScore = Math.min(
    100,
    Math.round(
      matchingSignals * 16 +
        leftRows.filter((x) => x.severity === "high").length * 9 +
        rightRows.filter((x) => x.severity === "high").length * 9,
    ),
  );

  return (
    <div className="border-t border-border bg-background/95 backdrop-blur-sm p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-[11px] text-muted-foreground tracking-wider">CROSS-BORDER CORRELATION</span>
        <span className="text-[11px] text-muted-foreground">Correlation score: {correlationScore}/100</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="rounded border border-border bg-card/40 p-2.5">
          <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">North Israel alerts</p>
          <ul className="space-y-1">
            {leftRows.map((row, idx) => (
              <li key={`left-${idx}`} className={`text-xs leading-relaxed ${severityClass[row.severity]}`}>
                - {row.label}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded border border-border bg-card/40 p-2.5">
          <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">South Lebanon activity</p>
          <ul className="space-y-1">
            {rightRows.map((row, idx) => (
              <li key={`right-${idx}`} className={`text-xs leading-relaxed ${severityClass[row.severity]}`}>
                - {row.label}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

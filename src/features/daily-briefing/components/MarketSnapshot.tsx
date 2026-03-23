import type { DailyBriefingData } from "@/features/daily-briefing/types/briefing.types";

interface MarketSnapshotProps {
  market: DailyBriefingData["market"];
}

function arrow(v: number): string {
  return v >= 0 ? "▲" : "▼";
}

export function MarketSnapshot({ market }: MarketSnapshotProps) {
  const rows = [market.brent, market.wti, market.gold].filter(Boolean);
  return (
    <section className="briefing-card p-3">
      <h3 className="briefing-mono mb-2 text-xs tracking-wider text-[var(--text-secondary)]">MARKET SNAPSHOT</h3>
      <div className="space-y-1.5">
        {rows.map((row) => (
          <div key={row?.label} className="flex items-center justify-between text-xs">
            <span>{row?.label}</span>
            <span className="briefing-mono">
              ${row?.value.toFixed(2)} {arrow(row?.changePct ?? 0)} {Math.abs(row?.changePct ?? 0).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
      {market.polymarket[0] && (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">
          Polymarket: <span className="briefing-mono">{market.polymarket[0].yesProbability}% YES</span>
        </p>
      )}
    </section>
  );
}

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { formatTimeAgo } from "@/lib/utils";

const FALLBACK_MARKETS = [
  { question: "US military strike on Iran in 2025?", probability: 0.34, volume: 0 },
  { question: "Iran nuclear weapon test by 2026?", probability: 0.12, volume: 0 },
  { question: "Oil price above $100/bbl by Q2?", probability: 0.47, volume: 0 },
  { question: "Israel strikes Iran by end of 2026?", probability: 0.35, volume: 0 },
];

interface PolymarketItem {
  question?: string;
  probability?: number;
  volume?: number;
  url?: string;
  end_date_iso?: string;
}

interface PredictionMarketsProps {
  polymarket?: PolymarketItem[] | null;
  fetchedAt?: string | null;
}

type SortMode = "volume" | "probability";
const TOP_N = 4;

function normalizePct(probability: number | undefined): number {
  let p = probability ?? 0;
  if (p > 1) p = p / 100;
  return Math.max(0, Math.min(100, Math.round(p * 100)));
}

function formatVolume(vol: number): string {
  if (vol >= 1_000_000) return `$${(vol / 1_000_000).toFixed(0)}m`;
  if (vol >= 1_000) return `$${(vol / 1_000).toFixed(0)}k`;
  return "$0";
}

function formatEndDate(iso: string | undefined): string | null {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return null;
  }
}

function ProbabilityBar({ pct }: { pct: number }) {
  const value = Math.max(0, Math.min(100, pct));
  return (
    <div className="w-full">
      <div className="h-1.5 rounded-full bg-muted relative overflow-hidden">
        <div
          className="h-full rounded-full bg-emerald-500"
          style={{ width: `${value}%` }}
        />
      </div>
      <div className="flex justify-between text-[11px] text-muted-foreground mt-0.5">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}

export function PredictionMarkets({ polymarket, fetchedAt }: PredictionMarketsProps) {
  const [sortMode, setSortMode] = useState<SortMode>("volume");

  const raw =
    polymarket && polymarket.length > 0
      ? polymarket
      : FALLBACK_MARKETS.map((m) => ({ ...m, url: undefined as string | undefined, end_date_iso: undefined as string | undefined }));

  const list = raw
    .slice()
    .sort((a, b) =>
      sortMode === "volume"
        ? (b.volume ?? 0) - (a.volume ?? 0) || normalizePct(b.probability) - normalizePct(a.probability)
        : normalizePct(b.probability) - normalizePct(a.probability) || (b.volume ?? 0) - (a.volume ?? 0),
    )
    .slice(0, TOP_N)
    .map((m) => ({
      question: m.question || "Market",
      pct: normalizePct(m.probability),
      volume: m.volume ?? 0,
      url: m.url,
      endLabel: formatEndDate(m.end_date_iso),
    }));

  const timeAgo = fetchedAt ? formatTimeAgo(fetchedAt) : null;

  return (
    <IntelPanel
      title="PREDICTION MARKETS"
      headerRight={
        <div className="flex gap-1">
          {(["volume", "probability"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setSortMode(mode)}
              className={`font-mono text-[11px] px-1.5 py-0.5 rounded transition-colors ${
                sortMode === mode
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
              }`}
            >
              {mode === "volume" ? "Vol" : "Prob"}
            </button>
          ))}
        </div>
      }
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {list.map((m, i) => (
          <div
            key={m.question ?? `market-${i}`}
            className="rounded-lg border border-border bg-muted/20 p-3 flex flex-col min-h-[180px]"
            role="article"
            aria-label={`${m.question} – ${m.pct}% YES probability`}
          >
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="font-mono text-[11px] text-muted-foreground">Polymarket</span>
              {m.url ? (
                <a
                  href={m.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-primary hover:underline inline-flex items-center gap-0.5"
                >
                  View Market
                  <ExternalLink className="h-3 w-3" />
                </a>
              ) : null}
            </div>
            <p className="text-xs font-semibold leading-tight line-clamp-2 mb-2">{m.question}</p>
            <div className="mt-auto space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-xl font-bold text-primary">{m.pct}%</span>
                <span className="text-[11px] text-muted-foreground text-right">
                  {formatVolume(m.volume)} Vol.
                </span>
              </div>
              <ProbabilityBar pct={m.pct} />
              <p className="text-[11px] text-muted-foreground">Implied YES probability</p>
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">
              {m.endLabel ? `Ends ${m.endLabel}` : "All time"}
            </p>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] text-muted-foreground">
          Source: Polymarket · Top {TOP_N} by {sortMode}
        </p>
        {timeAgo && (
          <p className="text-[11px] text-muted-foreground">Updated {timeAgo}</p>
        )}
      </div>
    </IntelPanel>
  );
}

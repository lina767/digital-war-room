import { ExternalLink } from "lucide-react";

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
}

interface PredictionMarketsProps {
  /** From FININT: polymarket array (probability 0–1). Show top 4 by importance (volume, then probability). */
  polymarket?: PolymarketItem[] | null;
}

const TOP_N = 4;

function formatVolume(vol: number): string {
  if (vol >= 1_000_000) return `$${(vol / 1_000_000).toFixed(0)}m`;
  if (vol >= 1_000) return `$${(vol / 1_000).toFixed(0)}k`;
  return "$0";
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
      <div className="flex justify-between text-[9px] text-muted-foreground mt-0.5">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}

export function PredictionMarkets({ polymarket }: PredictionMarketsProps) {
  const raw =
    polymarket && polymarket.length > 0
      ? polymarket
      : FALLBACK_MARKETS.map((m) => ({ ...m, url: undefined as string | undefined }));

  const list = raw
    .slice()
    .sort((a, b) => (b.volume ?? 0) - (a.volume ?? 0) || (b.probability ?? 0) - (a.probability ?? 0))
    .slice(0, TOP_N)
    .map((m) => ({
      question: m.question || "Market",
      probability: m.probability ?? 0,
      pct: Math.round((m.probability ?? 0) * 100),
      volume: m.volume ?? 0,
      url: m.url,
    }));

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-3">
      <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider">PREDICTION MARKETS</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {list.map((m, i) => (
          <div
            key={i}
            className="rounded-lg border border-border bg-muted/20 p-3 flex flex-col min-h-[180px]"
          >
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="font-mono text-[10px] text-muted-foreground">Polymarket</span>
              {m.url ? (
                <a
                  href={m.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-primary hover:underline inline-flex items-center gap-0.5"
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
                <span className="text-[10px] text-muted-foreground text-right">
                  {formatVolume(m.volume)} Vol.
                </span>
              </div>
              <ProbabilityBar pct={m.pct} />
              <p className="text-[9px] text-muted-foreground">Implied YES probability</p>
            </div>
            <p className="text-[9px] text-muted-foreground mt-1">All time</p>
          </div>
        ))}
      </div>
      <p className="text-[9px] text-muted-foreground">Source: Polymarket · Top 4 by volume</p>
    </div>
  );
}

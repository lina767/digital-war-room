import { ExternalLink, BarChart3 } from "lucide-react";

const FALLBACK_MARKETS = [
  { question: "US military strike on Iran in 2025?", probability: 0.34, volume: 0 },
  { question: "Iran nuclear weapon test by 2026?", probability: 0.12, volume: 0 },
  { question: "Oil price above $100/bbl by Q2?", probability: 0.47, volume: 0 },
];

interface PolymarketItem {
  question?: string;
  probability?: number;
  volume?: number;
  url?: string;
}

interface PredictionMarketsProps {
  /** From FININT: polymarket array (probability 0–1). Show top 3 by importance (volume, then probability). */
  polymarket?: PolymarketItem[] | null;
}

const TOP_N = 3;

function formatVolume(vol: number): string {
  if (vol >= 1_000_000) return `$${(vol / 1_000_000).toFixed(0)}m`;
  if (vol >= 1_000) return `$${(vol / 1_000).toFixed(0)}k`;
  return "$0";
}

/** Mini trend curve (no backend history; deterministic from current probability). */
function TrendSparklineFixed({ probability }: { probability: number }) {
  const pct = Math.min(100, Math.max(0, probability * 100));
  const points: number[] = [];
  const steps = 10;
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const y = 85 - pct * 0.75 * t * (1 + t * 0.3);
    points.push(y);
  }
  const pathD = points.map((y, i) => `${(i / steps) * 100},${y}`).join(" L ");
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-12 text-primary">
      <path
        d={`M ${pathD}`}
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.85}
      />
    </svg>
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
            <div className="flex items-start gap-2 mb-2">
              <div className="flex-shrink-0 w-8 h-8 rounded bg-primary/10 flex items-center justify-center">
                <BarChart3 className="h-4 w-4 text-primary" />
              </div>
              <div className="flex-1 min-w-0 h-12">
                <TrendSparklineFixed probability={m.probability} />
              </div>
            </div>
            <div className="mt-auto flex items-end justify-between gap-2">
              <span className="text-[10px] text-muted-foreground">
                {formatVolume(m.volume)} Vol.
              </span>
              <span className="font-mono text-lg font-bold text-primary">{m.pct}%</span>
            </div>
            <p className="text-[9px] text-muted-foreground mt-1">All time</p>
          </div>
        ))}
      </div>
      <p className="text-[9px] text-muted-foreground">Source: Polymarket · Top {TOP_N} by volume</p>
    </div>
  );
}

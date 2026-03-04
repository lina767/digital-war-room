const FALLBACK_MARKETS = [
  { question: "US military strike on Iran in 2025?", probability: 34 },
  { question: "Iran nuclear weapon test by 2026?", probability: 12 },
  { question: "Oil price above $100/bbl by Q2?", probability: 47 },
];

interface PolymarketItem {
  question?: string;
  probability?: number;
  url?: string;
}

interface PredictionMarketsProps {
  /** From FININT: polymarket array (probability 0–1, we show as %). First 3 are tracked Iran markets. */
  polymarket?: PolymarketItem[] | null;
}

export function PredictionMarkets({ polymarket }: PredictionMarketsProps) {
  const list =
    polymarket && polymarket.length > 0
      ? polymarket.slice(0, 8).map((m) => ({
          question: m.question || "Market",
          probability: Math.round((m.probability ?? 0) * 100),
          url: m.url,
        }))
      : FALLBACK_MARKETS.map((m) => ({ ...m, url: undefined }));

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2">
      <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider">PREDICTION MARKETS</h3>
      <div className="space-y-2">
        {list.map((m, i) => (
          <div key={i} className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              {m.url ? (
                <a
                  href={m.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] truncate max-w-[180px] hover:text-primary hover:underline"
                >
                  {m.question}
                </a>
              ) : (
                <span className="text-[11px] truncate max-w-[180px]">{m.question}</span>
              )}
              <span className="font-mono text-xs text-primary font-bold flex-shrink-0">{m.probability}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-secondary overflow-hidden">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${Math.min(100, m.probability)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="text-[9px] text-muted-foreground">Source: Polymarket</p>
    </div>
  );
}

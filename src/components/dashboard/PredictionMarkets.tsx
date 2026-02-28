const markets = [
  { question: "US military strike on Iran in 2025?", probability: 34 },
  { question: "Iran nuclear weapon test by 2026?", probability: 12 },
  { question: "Oil price above $100/bbl by Q2?", probability: 47 },
];

export function PredictionMarkets() {
  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2">
      <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider">PREDICTION MARKETS</h3>
      <div className="space-y-2">
        {markets.map((m, i) => (
          <div key={i} className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-[11px] truncate max-w-[180px]">{m.question}</span>
              <span className="font-mono text-xs text-primary font-bold ml-2">{m.probability}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-secondary overflow-hidden">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${m.probability}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="text-[9px] text-muted-foreground">Source: Polymarket</p>
    </div>
  );
}

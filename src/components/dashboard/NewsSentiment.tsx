export function NewsSentiment() {
  const sentiment = 35; // 0=bearish, 100=bullish

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider">MEDIA SENTIMENT</h3>
        <span className="text-[9px] text-muted-foreground">Updated 3m ago</span>
      </div>
      <div className="space-y-1.5">
        <div className="h-2.5 rounded-full w-full overflow-hidden" style={{ background: 'linear-gradient(to right, hsl(0 82% 56%), hsl(30 100% 50%), hsl(135 100% 50%))' }}>
          <div
            className="h-full w-0.5 bg-foreground rounded-full relative"
            style={{ marginLeft: `${sentiment}%` }}
          >
            <div className="absolute -top-1 -left-1 h-4 w-2 bg-foreground/80 rounded-sm" />
          </div>
        </div>
        <div className="flex justify-between font-mono text-[9px] text-muted-foreground">
          <span>Bearish</span>
          <span>Neutral</span>
          <span>Bullish</span>
        </div>
      </div>
    </div>
  );
}

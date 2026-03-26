interface SignalSummaryStripProps {
  showTheaterEvents: boolean;
  strikeCount: number;
  geointCount: number;
  aircraftCount: number;
  shipCount: number;
}

export function SignalSummaryStrip({
  showTheaterEvents,
  strikeCount,
  geointCount,
  aircraftCount,
  shipCount,
}: SignalSummaryStripProps) {
  const visible = geointCount > 0 || aircraftCount > 0 || shipCount > 0 || (showTheaterEvents && strikeCount > 0);
  if (!visible) return null;

  return (
    <div className="absolute top-2 left-2 flex items-center gap-2 bg-card/80 border border-border/50 rounded px-2 py-1 z-10 pointer-events-none">
      <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
      <span className="text-[11px] font-mono text-muted-foreground">
        {showTheaterEvents && strikeCount > 0 && `${strikeCount} STRIKES`}
        {showTheaterEvents && strikeCount > 0 && (geointCount > 0 || aircraftCount > 0 || shipCount > 0) && " · "}
        {geointCount > 0 && `${geointCount} THERMAL`}
        {geointCount > 0 && (aircraftCount > 0 || shipCount > 0) && " · "}
        {aircraftCount > 0 && `${aircraftCount} AC`}
        {aircraftCount > 0 && shipCount > 0 && " · "}
        {shipCount > 0 && `${shipCount} SHIPS`}
      </span>
    </div>
  );
}

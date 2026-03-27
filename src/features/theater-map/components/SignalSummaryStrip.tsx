interface SignalSummaryStripProps {
  showTheaterEvents: boolean;
  strikeCount: number;
  geointCount: number;
  aircraftCount: number;
  shipCount: number;
  /** When false, air/sea markers are hidden until SIGINT layer is toggled on. */
  sigintLayerOn?: boolean;
  /** Zoom map to ADS-B tracks and ensure SIGINT layer is visible. */
  onFitSigintTracks?: () => void;
}

export function SignalSummaryStrip({
  showTheaterEvents,
  strikeCount,
  geointCount,
  aircraftCount,
  shipCount,
  sigintLayerOn = true,
  onFitSigintTracks,
}: SignalSummaryStripProps) {
  const visible = geointCount > 0 || aircraftCount > 0 || shipCount > 0 || (showTheaterEvents && strikeCount > 0);
  if (!visible) return null;

  const showSigintHint = (aircraftCount > 0 || shipCount > 0) && !sigintLayerOn;
  const showFitBtn = Boolean(onFitSigintTracks) && (aircraftCount > 0 || shipCount > 0);

  return (
    <div className="absolute top-2 left-2 z-10 flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-2 bg-card/80 border border-border/50 rounded px-2 py-1 pointer-events-none">
        <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
        <span className="text-[11px] font-mono text-muted-foreground">
          {showTheaterEvents && strikeCount > 0 && `${strikeCount} STRIKES`}
          {showTheaterEvents && strikeCount > 0 && (geointCount > 0 || aircraftCount > 0 || shipCount > 0) && " · "}
          {geointCount > 0 && `${geointCount} THERMAL`}
          {geointCount > 0 && (aircraftCount > 0 || shipCount > 0) && " · "}
          {aircraftCount > 0 && `${aircraftCount} AC`}
          {aircraftCount > 0 && shipCount > 0 && " · "}
          {shipCount > 0 && `${shipCount} SHIPS`}
          {showSigintHint && " · SIGINT layer off"}
        </span>
      </div>
      {showFitBtn && (
        <button
          type="button"
          onClick={onFitSigintTracks}
          className="text-[11px] font-mono px-2 py-1 rounded border border-border bg-background/95 hover:bg-muted/60 text-foreground shadow-sm touch-manipulation"
          title="Show SIGINT layer, zoom map to aircraft and ships"
        >
          Fit ADS-B
        </button>
      )}
    </div>
  );
}

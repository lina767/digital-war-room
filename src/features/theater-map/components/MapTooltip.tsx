export interface MapTooltipData {
  content: string;
  color: string;
  x: number;
  y: number;
}

export function MapTooltip({ tooltip }: { tooltip: MapTooltipData | null }) {
  if (!tooltip) return null;
  return (
    <div
      className="fixed z-50 pointer-events-none px-2.5 py-1 rounded border bg-card/95 backdrop-blur-sm shadow-lg text-[11px] font-mono text-foreground whitespace-nowrap"
      style={{
        left: tooltip.x + 14,
        top: tooltip.y - 12,
        borderColor: tooltip.color,
      }}
    >
      {tooltip.content}
    </div>
  );
}

import { Plus, Minus } from "lucide-react";
import type { LayerVisibility } from "../config/layerVisibility";

export type StrikeTimeRange = "6h" | "24h" | "48h" | "7d" | "all";

export interface LegendRow {
  key: string;
  label: string;
  fill: string;
  count: number;
}

export interface LayerControlsProps {
  layers: LayerVisibility;
  toggleLayer: (layer: keyof LayerVisibility) => void;
  strikeTimeRange: StrikeTimeRange;
  onStrikeTimeRangeChange: (range: StrikeTimeRange) => void;
  theaterLoading: boolean;
  heatmapLoading: boolean;
  eventLegendItems: LegendRow[];
  attributionLegendItems: LegendRow[];
  onZoomIn: () => void;
  onZoomOut: () => void;
  sigintAirColor?: string;
  sigintSeaColor?: string;
}

const DEFAULT_SIGINT_AIR = "var(--map-sigint-air)";
const DEFAULT_SIGINT_SEA = "var(--map-sigint-sea)";

export function LayerControls({
  layers,
  toggleLayer,
  strikeTimeRange,
  onStrikeTimeRangeChange,
  theaterLoading,
  heatmapLoading,
  eventLegendItems,
  attributionLegendItems,
  onZoomIn,
  onZoomOut,
  sigintAirColor = DEFAULT_SIGINT_AIR,
  sigintSeaColor = DEFAULT_SIGINT_SEA,
}: LayerControlsProps) {
  const strikeRanges: StrikeTimeRange[] = ["6h", "24h", "48h", "7d", "all"];

  return (
    <>
      <div className="absolute top-2 right-2 flex flex-col gap-2 sm:gap-1 z-10 pointer-events-auto">
        <button
          type="button"
          onClick={onZoomIn}
          className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 sm:w-6 sm:h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors touch-manipulation"
          aria-label="Zoom in"
        >
          <Plus size={12} />
        </button>
        <button
          type="button"
          onClick={onZoomOut}
          className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 sm:w-6 sm:h-6 flex items-center justify-center rounded bg-card/80 border border-border/50 text-muted-foreground hover:text-foreground hover:bg-card transition-colors touch-manipulation"
          aria-label="Zoom out"
        >
          <Minus size={12} />
        </button>
      </div>

      <div className="absolute bottom-12 left-2 right-2 md:right-auto max-w-full overflow-x-auto overflow-y-hidden flex gap-2 flex-nowrap pb-1 md:overflow-visible md:flex-wrap md:gap-x-3 md:gap-y-2 md:pb-0 overflow-x-auto-touch items-center z-10 pointer-events-auto">
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground hidden sm:inline w-10">Events</span>
          <button
            type="button"
            onClick={() => toggleLayer("theaterEvents")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Strike markers (ACLED/FIRMS) – halos & colors by inferred side when text allows"
            aria-label={layers.theaterEvents ? "Hide theater event markers" : "Show theater event markers"}
          >
            <span
              className={`w-2.5 h-2.5 rounded-sm border ${layers.theaterEvents ? "bg-primary/40 border-primary" : "bg-muted/40 border-border"}`}
            />
            STRIKE
            {theaterLoading && layers.theaterEvents && <span className="animate-pulse">…</span>}
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("heatmap")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Conflict intensity from ACLED"
            aria-label={layers.heatmap ? "Hide heatmap layer" : "Show heatmap layer"}
          >
            <span
              className={`w-2.5 h-2.5 rounded-full border ${layers.heatmap ? "bg-red-500/60 border-red-500" : "bg-muted/40 border-border"}`}
            />
            HEAT
            {heatmapLoading && layers.heatmap && <span className="animate-pulse">…</span>}
          </button>
          <span
            className="text-[11px] font-mono text-muted-foreground ml-0.5"
            title="Time filter for strike-type markers (airstrike, missile, explosion, …)"
          >
            TIME
          </span>
          {strikeRanges.map((range) => {
            const isActive = strikeTimeRange === range;
            return (
              <button
                key={range}
                type="button"
                onClick={() => onStrikeTimeRangeChange(range)}
                className={`px-1.5 py-0.5 rounded border text-[10px] font-mono uppercase transition-colors touch-manipulation ${
                  isActive
                    ? "bg-destructive/20 border-destructive/60 text-foreground"
                    : "bg-card/60 border-border/70 text-muted-foreground hover:text-foreground"
                }`}
                aria-label={`Filter strike events by time window ${range.toUpperCase()}`}
              >
                {range.toUpperCase()}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0 border-l border-border/50 pl-2">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground hidden sm:inline w-8">SAM</span>
          <button
            type="button"
            onClick={() => toggleLayer("samRings")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="SAM engagement zones"
            aria-label={layers.samRings ? "Hide SAM rings layer" : "Show SAM rings layer"}
          >
            <span
              className={`w-2.5 h-2.5 rounded-full border ${layers.samRings ? "border-destructive" : "border-border"}`}
              style={
                layers.samRings
                  ? { borderColor: "hsl(var(--destructive))", background: "hsl(var(--destructive) / 0.2)" }
                  : {}
              }
            />
            ZONES
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("militaryBases")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Military base overlay"
            aria-label={layers.militaryBases ? "Hide military base layer" : "Show military base layer"}
          >
            <span
              className="w-2.5 h-2.5 border"
              style={
                layers.militaryBases
                  ? { borderColor: "hsl(210 90% 62%)", background: "hsl(210 90% 62% / 0.25)" }
                  : { borderColor: "hsl(var(--border))" }
              }
            />
            MB
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("nuclearFacilities")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Nuclear facility overlay"
            aria-label={layers.nuclearFacilities ? "Hide nuclear facility layer" : "Show nuclear facility layer"}
          >
            <span
              className="w-2.5 h-2.5 rounded-full border"
              style={
                layers.nuclearFacilities
                  ? { borderColor: "hsl(43 95% 56%)", background: "hsl(43 95% 56% / 0.25)" }
                  : { borderColor: "hsl(var(--border))" }
              }
            />
            NUC
          </button>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0 border-l border-border/50 pl-2">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground hidden sm:inline">Trade</span>
          <button
            type="button"
            onClick={() => toggleLayer("airRoutes")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Main air corridors"
            aria-label={layers.airRoutes ? "Hide air corridors layer" : "Show air corridors layer"}
          >
            <svg width="12" height="10" viewBox="-1.2 -1 2.4 2" className="shrink-0" style={{ color: layers.airRoutes ? "hsl(210 80% 55%)" : undefined }}>
              <polygon points="0,-1 0.65,0.35 0.45,1 0,0.55 -0.45,1 -1.2,0.35" fill="currentColor" stroke="currentColor" strokeWidth="0.15" />
            </svg>
            AIR
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("seaLanes")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Sea lanes"
            aria-label={layers.seaLanes ? "Hide sea lanes layer" : "Show sea lanes layer"}
          >
            <svg width="12" height="10" viewBox="-1.2 -0.5 2.4 1.2" className="shrink-0" style={{ color: layers.seaLanes ? "hsl(160 70% 45%)" : undefined }}>
              <path d="M -1.1 0.25 L -0.6 0.5 L 1 0.5 L 1.2 0.2 L 0.8 -0.1 L -0.9 -0.05 Z" fill="currentColor" stroke="currentColor" strokeWidth="0.1" />
            </svg>
            SEA
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("chokepoints")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Chokepoint zones"
            aria-label={layers.chokepoints ? "Hide chokepoints layer" : "Show chokepoints layer"}
          >
            <span
              className="w-2.5 h-2.5 rounded-sm border"
              style={
                layers.chokepoints
                  ? { borderColor: "hsl(200 70% 50%)", background: "hsl(200 70% 50% / 0.25)" }
                  : { borderColor: "hsl(var(--border))" }
              }
            />
            CHP
          </button>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0 border-l border-border/50 pl-2">
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground hidden sm:inline w-8">Intel</span>
          <button
            type="button"
            onClick={() => toggleLayer("geoint")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            aria-label={layers.geoint ? "Hide GEOINT layer" : "Show GEOINT layer"}
          >
            <span style={{ color: layers.geoint ? "var(--map-geoint)" : undefined }}>△</span>
            GEOINT
          </button>
          <button
            type="button"
            onClick={() => toggleLayer("sigint")}
            className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors touch-manipulation flex-shrink-0"
            title="Live tracks: Air / Sea"
            aria-label={layers.sigint ? "Hide SIGINT layer (air and sea tracks)" : "Show SIGINT layer (air and sea tracks)"}
          >
            <svg width="12" height="10" viewBox="-1.2 -1 2.4 2" className="shrink-0" style={{ color: layers.sigint ? sigintAirColor : undefined }}>
              <polygon points="0,-1 0.65,0.35 0.45,1 0,0.55 -0.45,1 -1.2,0.35" fill="currentColor" stroke="currentColor" strokeWidth="0.15" />
            </svg>
            <svg width="12" height="10" viewBox="-1.2 -0.5 2.4 1.2" className="shrink-0" style={{ color: layers.sigint ? sigintSeaColor : undefined }}>
              <path d="M -1.1 0.25 L -0.6 0.5 L 1 0.5 L 1.2 0.2 L 0.8 -0.1 L -0.9 -0.05 Z" fill="currentColor" stroke="currentColor" strokeWidth="0.1" />
            </svg>
            SIGINT
          </button>
        </div>
        {(layers.airRoutes || layers.seaLanes) && (
          <div className="flex items-center gap-2 flex-wrap">
            {layers.airRoutes && (
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: "hsl(210 80% 55%)" }} title="Air corridors" />
                <span className="text-[11px] font-mono text-muted-foreground">Air corridors</span>
              </div>
            )}
            {layers.seaLanes && (
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: "hsl(160 70% 45%)" }} title="Sea lanes" />
                <span className="text-[11px] font-mono text-muted-foreground">Sea lanes</span>
              </div>
            )}
          </div>
        )}
        {attributionLegendItems.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap border-l border-border/50 pl-2">
            {attributionLegendItems.map(({ key, label, fill }) => (
              <div key={key} className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full ring-1 ring-white/20" style={{ backgroundColor: fill }} title={label} />
                <span className="text-[11px] font-mono text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>
        )}
        {eventLegendItems.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            {eventLegendItems.map(({ key, label, fill }) => (
              <div key={key} className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-sm" style={{ backgroundColor: fill }} title={label} />
                <span className="text-[11px] font-mono text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

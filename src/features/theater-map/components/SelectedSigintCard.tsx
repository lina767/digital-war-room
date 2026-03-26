import { X } from "lucide-react";
import type { SigintAircraft, SigintShip } from "@/types/theaterMap";

type SelectedSigint =
  | { type: "aircraft"; data: SigintAircraft }
  | { type: "ship"; data: SigintShip };

interface SelectedSigintCardProps {
  selectedSigint: SelectedSigint;
  onClose: () => void;
  sigintAirColor: string;
  sigintSeaColor: string;
}

export function SelectedSigintCard({
  selectedSigint,
  onClose,
  sigintAirColor,
  sigintSeaColor,
}: SelectedSigintCardProps) {
  return (
    <div
      className="absolute bottom-24 left-2 right-2 sm:left-auto sm:right-2 sm:max-w-xs sm:w-[260px] rounded-lg border border-border bg-card/95 backdrop-blur-sm shadow-lg p-3 space-y-2 z-10 pointer-events-auto"
      style={selectedSigint.type === "aircraft" ? { borderColor: sigintAirColor } : { borderColor: sigintSeaColor }}
    >
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="flex flex-col min-w-0 flex-1">
          <span className="font-mono text-[11px] text-muted-foreground tracking-wider uppercase">Track detail</span>
          <span className="text-xs font-semibold truncate">
            {selectedSigint.type === "aircraft" ? selectedSigint.data.flight : selectedSigint.data.name}
          </span>
        </div>
        <button
          type="button"
          aria-label="Close track details"
          className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 sm:h-6 sm:w-6 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 touch-manipulation flex-shrink-0"
          onClick={onClose}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        <span>Type</span>
        <span className="text-right">
          {selectedSigint.type === "aircraft" ? (selectedSigint.data.category ?? "–") : (selectedSigint.data.type ?? "–")}
        </span>
        {selectedSigint.type === "aircraft" && selectedSigint.data.country && (
          <>
            <span>Country</span>
            <span className="text-right">{selectedSigint.data.country}</span>
          </>
        )}
        <span>Location</span>
        <span className="text-right">
          {selectedSigint.data.lon.toFixed(1)}E · {selectedSigint.data.lat.toFixed(1)}N
        </span>
      </div>
    </div>
  );
}

import { X } from "lucide-react";
import type { TheaterEvent } from "@/lib/api";
import type { StrikeAttribution } from "@/components/dashboard/mapConfig";

interface SelectedEventCardProps {
  selectedEvent: TheaterEvent;
  selectedStrikeAttr: StrikeAttribution;
  eventStyles: Record<string, { label: string; fill: string; stroke: string }>;
  attributionStyles: Record<StrikeAttribution, { label: string; fill: string; stroke: string }>;
  onClose: () => void;
}

export function SelectedEventCard({
  selectedEvent,
  selectedStrikeAttr,
  eventStyles,
  attributionStyles,
  onClose,
}: SelectedEventCardProps) {
  return (
    <div className="absolute bottom-24 left-2 right-2 sm:left-auto sm:right-2 sm:max-w-xs sm:w-[280px] rounded-lg border border-border bg-card/95 backdrop-blur-sm shadow-lg p-3 space-y-2 max-h-[60vh] overflow-y-auto z-10 pointer-events-auto">
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="flex flex-col min-w-0 flex-1">
          <span className="font-mono text-[11px] text-muted-foreground tracking-wider uppercase">Event detail</span>
          <span className="text-xs font-semibold truncate">{eventStyles[selectedEvent.event_type]?.label ?? selectedEvent.event_type}</span>
        </div>
        <button
          type="button"
          aria-label="Close escalation details"
          className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 sm:h-6 sm:w-6 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 touch-manipulation flex-shrink-0"
          onClick={onClose}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      {selectedEvent.label && <p className="text-[11px] leading-snug text-foreground/90">{selectedEvent.label}</p>}
      {selectedEvent.sub_event_type != null && selectedEvent.sub_event_type !== "" && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          <span className="text-muted-foreground">Detail</span>
          <span className="text-right text-foreground/90">{selectedEvent.sub_event_type}</span>
        </div>
      )}
      {(selectedEvent.country || selectedEvent.admin1) && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          {selectedEvent.country && (
            <>
              <span className="text-muted-foreground">Country</span>
              <span className="text-right text-foreground/90">{selectedEvent.country}</span>
            </>
          )}
          {selectedEvent.admin1 && (
            <>
              <span className="text-muted-foreground">Region</span>
              <span className="text-right text-foreground/90">{selectedEvent.admin1}</span>
            </>
          )}
        </div>
      )}
      <div className="space-y-0.5">
        <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">Casualties</span>
        <div className="text-[11px] text-foreground/90">
          {selectedEvent.fatalities != null ||
          selectedEvent.deaths_civilians != null ||
          selectedEvent.deaths_a != null ||
          selectedEvent.deaths_b != null ? (
            <>
              {selectedEvent.fatalities != null && <p>Total reported: {selectedEvent.fatalities} fatality/fatalities</p>}
              {selectedEvent.deaths_civilians != null && <p>Civilian: {selectedEvent.deaths_civilians}</p>}
              {(selectedEvent.deaths_a != null || selectedEvent.deaths_b != null) && (
                <p>
                  Military/actors: {[selectedEvent.deaths_a, selectedEvent.deaths_b].filter((n): n is number => n != null).join(" / ")}
                  {selectedEvent.side_a != null && selectedEvent.side_b != null && (
                    <span className="text-muted-foreground">
                      {" "}
                      ({selectedEvent.side_a} / {selectedEvent.side_b})
                    </span>
                  )}
                </p>
              )}
            </>
          ) : selectedEvent.source === "FIRMS" ? (
            <p>No casualty data (satellite thermal anomaly only).</p>
          ) : (
            <p>No casualty data reported.</p>
          )}
        </div>
      </div>
      {selectedStrikeAttr !== "unknown" && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          <span className="text-muted-foreground">Map attribution</span>
          <span className="text-right text-foreground/90">{attributionStyles[selectedStrikeAttr].label}</span>
        </div>
      )}
      {(selectedEvent.actor1 != null || selectedEvent.actor2 != null || selectedEvent.side_a != null || selectedEvent.side_b != null) && (
        <div className="space-y-0.5">
          <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">Actors</span>
          <p className="text-[11px] text-foreground/90">
            {selectedEvent.actor1 != null || selectedEvent.actor2 != null
              ? [selectedEvent.actor1, selectedEvent.actor2].filter(Boolean).join(" · ")
              : selectedEvent.side_a != null || selectedEvent.side_b != null
                ? `${selectedEvent.side_a ?? "–"} vs ${selectedEvent.side_b ?? "–"}`
                : "–"}
          </p>
        </div>
      )}
      {(selectedEvent.event_date != null || selectedEvent.date_start != null) && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          <span className="text-muted-foreground">Date</span>
          <span className="text-right text-foreground/90">{selectedEvent.event_date ?? selectedEvent.date_start ?? "–"}</span>
        </div>
      )}
      <div className="space-y-0.5">
        <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">Reporting / context</span>
        <p className="text-[11px] text-foreground/90 leading-snug line-clamp-4">
          {selectedEvent.notes != null && selectedEvent.notes !== ""
            ? selectedEvent.notes
            : selectedEvent.source === "FIRMS"
              ? "Satellite detection (VIIRS). No linked news reporting."
              : "No additional reporting."}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        <span>Source</span>
        <span className="text-right">{selectedEvent.source ?? "FIRMS/ACLED"}</span>
        <span>Confidence</span>
        <span className="text-right">{selectedEvent.confidence ?? "n/a"}</span>
        <span>Location</span>
        <span className="text-right">
          {selectedEvent.lon.toFixed(1)}°E · {selectedEvent.lat.toFixed(1)}°N
        </span>
      </div>
      {selectedEvent.url != null && selectedEvent.url !== "" && (
        <a
          href={selectedEvent.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-[11px] text-primary hover:underline"
        >
          {selectedEvent.source === "FIRMS" ? "Open EO Browser (satellite imagery)" : "Open source"}
          <span aria-hidden>↗</span>
        </a>
      )}
    </div>
  );
}

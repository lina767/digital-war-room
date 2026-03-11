import { Button } from "@/components/ui/button";
import { DailyBriefing } from "@/components/dashboard/DailyBriefing";
import { GlobalImpactPanel } from "@/components/dashboard/GlobalImpactPanel";
import { LatestHeadlines } from "@/components/dashboard/LatestHeadlines";
import { EventsTimeline } from "@/components/dashboard/EventsTimeline";
import { EvidenceCard } from "@/components/dashboard/EvidenceCard";
import { NewsSentiment } from "@/components/dashboard/NewsSentiment";
import { InternetConnectivity } from "@/components/dashboard/InternetConnectivity";
import { FlightRadar } from "@/components/dashboard/FlightRadar";
import { PredictionMarkets } from "@/components/dashboard/PredictionMarkets";
import { NarrativeSignalPanel } from "@/components/dashboard/NarrativeSignalPanel";
import type { ProximityEvidence } from "@/lib/proximityAnalyzerService";
import { Target, X } from "lucide-react";

interface DashboardRightPanelProps {
  rightPanelOpen: boolean;
  setRightPanelOpen: (open: boolean) => void;
  conflictData: any;
  lastUpdated: Date | null;
  displayConflictLabel: string;
  /** True while initial load of cached analysis is in progress */
  analysisLoading?: boolean;
  proximityEvidence: ProximityEvidence[];
  proximityLoading: boolean;
  proximityError: string | null;
  runProximity: () => void;
}

export function DashboardRightPanel({
  rightPanelOpen,
  setRightPanelOpen,
  conflictData,
  lastUpdated,
  displayConflictLabel,
  analysisLoading,
  proximityEvidence,
  proximityLoading,
  proximityError,
  runProximity,
}: DashboardRightPanelProps) {
  return (
    <aside
      className={`
          ${rightPanelOpen ? "translate-x-0" : "translate-x-full"}
          md:translate-x-0
          w-[min(18rem,90vw)] sm:w-72 md:min-w-[340px] md:flex-1 md:min-w-0 border-l border-border flex-shrink-0 p-4 flex flex-col overflow-y-auto bg-background
          absolute md:relative inset-y-0 right-0 z-20
          transition-transform duration-300 ease-in-out
        `}
    >
      <div className="flex items-center justify-between mb-3 gap-2">
        <h2 className="font-mono text-xs text-muted-foreground tracking-wider truncate">INTELLIGENCE FEED</h2>
        <button
          type="button"
          aria-label="Close panel"
          className="md:hidden min-h-11 min-w-11 flex items-center justify-center -m-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 active:bg-muted touch-manipulation"
          onClick={() => setRightPanelOpen(false)}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-4">
        <DailyBriefing data={conflictData} conflictLabel={displayConflictLabel} lastUpdated={lastUpdated} isLoading={analysisLoading} />
        <GlobalImpactPanel data={conflictData} />
        <NarrativeSignalPanel data={conflictData} conflictLabel={displayConflictLabel} />
        <LatestHeadlines data={conflictData} maxItems={15} />
        <EventsTimeline data={conflictData} />
      </div>

      {/* Proximity Analyzer: strike–civilian correlation */}
      <div className="pt-4 border-t border-border">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider flex items-center gap-1.5">
            <Target className="h-3.5 w-3.5" />
            PROXIMITY ANALYZER
          </h3>
          <Button
            size="sm"
            variant="outline"
            className="text-xs min-h-9 sm:min-h-7 touch-manipulation"
            disabled={proximityLoading}
            onClick={runProximity}
            title="Correlate FIRMS strikes with civilian infrastructure (Overpass)"
          >
            {proximityLoading ? "Running…" : "Run"}
          </Button>
        </div>
        {proximityError && <p className="text-xs text-destructive mb-2">{proximityError}</p>}
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {proximityEvidence.length === 0 && !proximityLoading && !proximityError && (
            <p className="text-xs text-muted-foreground py-2">
              Click Run to correlate thermal anomalies with schools, hospitals, etc.
            </p>
          )}
          {proximityEvidence.map((e, i) => (
            <EvidenceCard key={`${e.strikeLat}-${e.strikeLon}-${e.facilityName}-${i}`} evidence={e} />
          ))}
        </div>
      </div>

      {/* Activity & Connectivity (Iran Monitor style) */}
      <div className="mt-4 pt-4 border-t border-border">
        <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider mb-3">ACTIVITY & CONNECTIVITY</h3>
        <div className="space-y-3">
          <NewsSentiment newsScore={conflictData?.news?.news_score} lastUpdated={lastUpdated} />
          <InternetConnectivity />
          <FlightRadar />
          <PredictionMarkets polymarket={conflictData?.finint?.polymarket} />
        </div>
      </div>

      <p className="mt-4 pt-3 border-t border-border text-[10px] text-muted-foreground">
        Data sources: News API · GDELT · RSS · Polymarket · ADSB · VesselFinder · NASA FIRMS · ReliefWeb · Shodan · IODA
      </p>
    </aside>
  );
}


import { UpdatedBriefing } from "@/components/dashboard/UpdatedBriefing";
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
  /** Proximity evidence from main analysis (runs automatically with other agents) */
  proximityEvidence: ProximityEvidence[];
}

export function DashboardRightPanel({
  rightPanelOpen,
  setRightPanelOpen,
  conflictData,
  lastUpdated,
  displayConflictLabel,
  analysisLoading,
  proximityEvidence,
}: DashboardRightPanelProps) {
  return (
    <aside
      className={`
          ${rightPanelOpen ? "translate-x-0" : "translate-x-full"}
          md:translate-x-0
          w-[min(18rem,90vw)] sm:w-72 md:min-w-[380px] md:flex-[1_1_40%] md:min-w-0 border-l border-border flex-shrink-0 p-4 flex flex-col overflow-y-auto bg-background
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
        <UpdatedBriefing data={conflictData} conflictLabel={displayConflictLabel} lastUpdated={lastUpdated} isLoading={analysisLoading} />
        <GlobalImpactPanel data={conflictData} />
        <NarrativeSignalPanel data={conflictData} conflictLabel={displayConflictLabel} />
        <LatestHeadlines data={conflictData} maxItems={15} />
        <EventsTimeline data={conflictData} />
      </div>

      {/* Proximity Analyzer: strike–civilian correlation (runs automatically with main analysis) */}
      <div className="pt-4 border-t border-border">
        <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider flex items-center gap-1.5 mb-2">
          <Target className="h-3.5 w-3.5" />
          PROXIMITY ANALYZER
        </h3>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {analysisLoading && proximityEvidence.length === 0 && (
            <p className="text-xs text-muted-foreground py-2 italic">Running with analysis…</p>
          )}
          {!analysisLoading && proximityEvidence.length === 0 && (
            <p className="text-xs text-muted-foreground py-2">
              Strike–civilian correlation from latest analysis. No proximity evidence in current window.
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


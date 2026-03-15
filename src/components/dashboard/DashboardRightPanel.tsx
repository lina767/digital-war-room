import { UpdatedBriefing } from "@/components/dashboard/UpdatedBriefing";
import { SignalFrameworkPanel } from "@/components/dashboard/SignalFrameworkPanel";
import { GlobalImpactPanel } from "@/components/dashboard/GlobalImpactPanel";
import { ChokePointPanel } from "@/components/dashboard/ChokePointPanel";
import { LatestHeadlines } from "@/components/dashboard/LatestHeadlines";
import { EventsTimeline } from "@/components/dashboard/EventsTimeline";
import { EvidenceCard } from "@/components/dashboard/EvidenceCard";
import { NewsSentiment } from "@/components/dashboard/NewsSentiment";
import { InternetConnectivity } from "@/components/dashboard/InternetConnectivity";
import { FlightRadar } from "@/components/dashboard/FlightRadar";
import { IAEATrackerPanel } from "@/components/dashboard/IAEATrackerPanel";
import { GreyNoisePanel } from "@/components/dashboard/GreyNoisePanel";
import { PredictionMarkets } from "@/components/dashboard/PredictionMarkets";
import { PredictivePanel } from "@/components/dashboard/PredictivePanel";
import { CompliancePanel } from "@/components/dashboard/CompliancePanel";
import { WorldMap } from "@/components/dashboard/WorldMap";
import type { ProximityEvidence } from "@/lib/proximityAnalyzerService";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { Target, X, Globe } from "lucide-react";
import { IntelPanelSkeleton } from "@/components/dashboard/IntelPanel";

interface ProximityAnalyzerBlockProps {
  analysisLoading?: boolean;
  proximityEvidence: ProximityEvidence[];
  proximitySummary?: string;
  reasonEmpty?: string;
  errorMessage?: string;
}

function ProximityAnalyzerBlock({
  analysisLoading,
  proximityEvidence,
  proximitySummary,
  reasonEmpty,
  errorMessage,
}: ProximityAnalyzerBlockProps) {
  const evidence = proximityEvidence;
  const reason = reasonEmpty;
  const errMsg = errorMessage;
  const summary = proximitySummary;

  const isError = typeof summary === "string" && summary.startsWith("PROXIMITY error:");

  return (
    <div className="pt-4 border-t border-border">
      <div className="flex items-center justify-between gap-2 mb-2">
        <h3 className="font-mono text-[11px] text-muted-foreground tracking-wider flex items-center gap-1.5">
          <Target className="h-3.5 w-3.5" />
          PROXIMITY ANALYZER
        </h3>
        <span className="text-[10px] text-muted-foreground/80 font-mono">with analysis</span>
      </div>
      <div className="space-y-2 max-h-64 overflow-y-auto overscroll-contain">
        {analysisLoading && evidence.length === 0 && (
          <p className="text-xs text-muted-foreground py-2 italic">Running with analysis…</p>
        )}
        {!analysisLoading && evidence.length === 0 && (
          <>
            {isError && (
              <p className="text-xs text-destructive py-2">{summary}</p>
            )}
            {!isError && reason === "no_strikes" && (
              <p className="text-xs text-muted-foreground py-2">
                No thermal anomalies in region (check NASA FIRMS key and region).
                {errMsg && <span className="block mt-1 text-destructive/90">{errMsg}</span>}
              </p>
            )}
            {!isError && reason === "no_facilities_near_strikes" && (
              <p className="text-xs text-muted-foreground py-2">
                Strikes in window but no schools/hospitals within 300 m in OSM.
              </p>
            )}
            {!isError && reason !== "no_strikes" && reason !== "no_facilities_near_strikes" && (
              <p className="text-xs text-muted-foreground py-2">
                Strike–civilian correlation from latest analysis. No proximity evidence in current window.
              </p>
            )}
          </>
        )}
        {evidence.length > 0 &&
          evidence.map((e, i) => (
            <EvidenceCard key={`${e.strikeLat}-${e.strikeLon}-${e.facilityName}-${i}`} evidence={e} />
          ))}
      </div>
    </div>
  );
}

interface DashboardRightPanelProps {
  rightPanelOpen: boolean;
  setRightPanelOpen: (open: boolean) => void;
  conflictData: ConflictData | null;
  lastUpdated: Date | null;
  displayConflictLabel: string;
  /** Current conflict for world map highlight */
  activeConflict?: string | null;
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
  activeConflict = null,
  analysisLoading,
  proximityEvidence,
}: DashboardRightPanelProps) {
  return (
    <aside
      className={`
          ${rightPanelOpen ? "translate-x-0" : "translate-x-full"}
          md:translate-x-0
          w-[min(18rem,90vw)] sm:w-72 md:min-w-[380px] md:flex-[1_1_40%] md:min-w-0 border-l border-border flex-shrink-0 p-4 flex flex-col overflow-y-auto overscroll-contain bg-background
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

      {/* World map overview – integrated in right panel */}
      <div className="mb-4 rounded-lg border border-border overflow-hidden bg-card/30">
        <div className="px-2 py-1.5 border-b border-border flex items-center gap-1.5">
          <Globe className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="font-mono text-[11px] text-muted-foreground tracking-wider">WORLD OVERVIEW</span>
        </div>
        <div className="h-36 sm:h-40 md:h-44 relative">
          <WorldMap />
        </div>
      </div>

      <div className="space-y-4">
        {analysisLoading && !conflictData ? (
          <>
            <IntelPanelSkeleton lines={4} />
            <IntelPanelSkeleton lines={3} />
            <IntelPanelSkeleton lines={3} />
            <IntelPanelSkeleton lines={2} />
          </>
        ) : (
          <>
            <UpdatedBriefing data={conflictData} conflictLabel={displayConflictLabel} lastUpdated={lastUpdated} isLoading={analysisLoading} />
            <SignalFrameworkPanel data={conflictData} activeConflict={activeConflict} />
            <PredictivePanel data={conflictData} />
            <CompliancePanel data={conflictData} />
            <ChokePointPanel data={conflictData} />
            <GlobalImpactPanel data={conflictData} />
            <LatestHeadlines data={conflictData} maxItems={15} />
            <EventsTimeline data={conflictData} />
          </>
        )}
      </div>

      <ProximityAnalyzerBlock
        analysisLoading={analysisLoading}
        proximityEvidence={proximityEvidence}
        proximitySummary={conflictData?.proximity?.summary}
        reasonEmpty={conflictData?.proximity?.reason_empty}
        errorMessage={conflictData?.proximity?.error_message}
      />

      {/* Activity & Connectivity (Iran Monitor style) */}
      <div className="mt-4 pt-4 border-t border-border">
        <h3 className="font-mono text-[11px] text-muted-foreground tracking-wider mb-3">ACTIVITY & CONNECTIVITY</h3>
        <div className="space-y-3">
          <GreyNoisePanel conflict={activeConflict || "Iran"} />
          <NewsSentiment newsScore={conflictData?.news?.news_score} lastUpdated={lastUpdated} />
          <InternetConnectivity />
          <IAEATrackerPanel />
          <FlightRadar sigint={conflictData?.sigint} />
          <PredictionMarkets polymarket={conflictData?.finint?.polymarket} fetchedAt={conflictData?.finint?.polymarket_fetched_at} />
        </div>
      </div>

      <p className="mt-4 pt-3 border-t border-border text-[11px] text-muted-foreground">
        Data sources: News API · GDELT · RSS · Polymarket · ADSB · VesselFinder · NASA FIRMS · ReliefWeb · Shodan · IODA · GreyNoise · FAO · EIA · AIS
      </p>
    </aside>
  );
}


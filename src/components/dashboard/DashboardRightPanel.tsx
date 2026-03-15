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
import { GreyNoisePanel } from "@/components/dashboard/GreyNoisePanel";
import { PredictionMarkets } from "@/components/dashboard/PredictionMarkets";
import { PredictivePanel } from "@/components/dashboard/PredictivePanel";
import { CompliancePanel } from "@/components/dashboard/CompliancePanel";
import { WorldMap } from "@/components/dashboard/WorldMap";
import { useState } from "react";
import type { ProximityEvidence } from "@/lib/proximityAnalyzerService";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { getApiBase } from "@/lib/api";
import { Target, X, Globe, Play } from "lucide-react";
import { IntelPanelSkeleton } from "@/components/dashboard/IntelPanel";

function regionFromConflict(conflict: string | null | undefined): string {
  const c = (conflict || "").toLowerCase();
  if (c.includes("ukraine") || c.includes("russia")) return "eastern_europe";
  if (c.includes("gaza") || c.includes("israel")) return "gaza_israel";
  if (c.includes("yemen")) return "yemen";
  return "middle_east";
}

interface ProximityAnalyzerBlockProps {
  analysisLoading?: boolean;
  proximityEvidence: ProximityEvidence[];
  proximitySummary?: string;
  reasonEmpty?: string;
  errorMessage?: string;
  activeConflict?: string | null;
}

function ProximityAnalyzerBlock({
  analysisLoading,
  proximityEvidence,
  proximitySummary,
  reasonEmpty,
  errorMessage,
  activeConflict,
}: ProximityAnalyzerBlockProps) {
  const [onDemand, setOnDemand] = useState<{
    evidence: ProximityEvidence[];
    reason_empty?: string;
    error_message?: string;
  } | null>(null);
  const [onDemandLoading, setOnDemandLoading] = useState(false);

  const evidence = onDemand !== null ? onDemand.evidence : proximityEvidence;
  const reason = onDemand !== null ? onDemand.reason_empty : reasonEmpty;
  const errMsg = onDemand !== null ? onDemand.error_message : errorMessage;
  const summary = proximitySummary;

  const isError = typeof summary === "string" && summary.startsWith("PROXIMITY error:");

  async function handleRunProximity() {
    setOnDemandLoading(true);
    setOnDemand(null);
    try {
      const region = regionFromConflict(activeConflict);
      const res = await fetch(
        `${getApiBase()}/api/proximity/analyze?region=${encodeURIComponent(region)}&days=3`,
        { signal: AbortSignal.timeout(120_000) }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as {
        evidence?: ProximityEvidence[];
        reason_empty?: string;
        error_message?: string;
      };
      setOnDemand({
        evidence: Array.isArray(data.evidence) ? data.evidence : [],
        reason_empty: data.reason_empty,
        error_message: data.error_message,
      });
    } catch (e) {
      setOnDemand({
        evidence: [],
        reason_empty: "error",
        error_message: e instanceof Error ? e.message : "Request failed",
      });
    } finally {
      setOnDemandLoading(false);
    }
  }

  return (
    <div className="pt-4 border-t border-border">
      <div className="flex items-center justify-between gap-2 mb-2">
        <h3 className="font-mono text-[11px] text-muted-foreground tracking-wider flex items-center gap-1.5">
          <Target className="h-3.5 w-3.5" />
          PROXIMITY ANALYZER
        </h3>
        <button
          type="button"
          onClick={handleRunProximity}
          disabled={onDemandLoading}
          aria-label="Run proximity analysis"
          className="flex items-center gap-1 rounded border border-border bg-muted/50 px-2 py-1 text-[11px] font-mono text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-50"
        >
          <Play className="h-3 w-3" />
          {onDemandLoading ? "…" : "Run"}
        </button>
      </div>
      <div className="space-y-2 max-h-64 overflow-y-auto overscroll-contain">
        {onDemandLoading && (
          <p className="text-xs text-muted-foreground py-2 italic">Running proximity analysis…</p>
        )}
        {!onDemandLoading && analysisLoading && evidence.length === 0 && onDemand === null && (
          <p className="text-xs text-muted-foreground py-2 italic">Running with analysis…</p>
        )}
        {!analysisLoading && evidence.length === 0 && onDemand === null && (
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
        {evidence.length === 0 && onDemand !== null && (
          <>
            {reason === "no_strikes" && (
              <p className="text-xs text-muted-foreground py-2">
                No thermal anomalies in region (check NASA FIRMS key and region).
                {errMsg && <span className="block mt-1 text-destructive/90">{errMsg}</span>}
              </p>
            )}
            {reason === "no_facilities_near_strikes" && (
              <p className="text-xs text-muted-foreground py-2">
                Strikes in window but no schools/hospitals within 300 m in OSM.
              </p>
            )}
            {reason === "error" && errMsg && (
              <p className="text-xs text-destructive py-2">{errMsg}</p>
            )}
            {reason !== "no_strikes" && reason !== "no_facilities_near_strikes" && reason !== "error" && (
              <p className="text-xs text-muted-foreground py-2">No proximity evidence in this run.</p>
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
        <div className="h-40 sm:h-44 relative">
          <WorldMap activeConflict={activeConflict} />
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
        activeConflict={activeConflict}
      />

      {/* Activity & Connectivity (Iran Monitor style) */}
      <div className="mt-4 pt-4 border-t border-border">
        <h3 className="font-mono text-[11px] text-muted-foreground tracking-wider mb-3">ACTIVITY & CONNECTIVITY</h3>
        <div className="space-y-3">
          <GreyNoisePanel conflict={activeConflict || "Iran"} />
          <NewsSentiment newsScore={conflictData?.news?.news_score} lastUpdated={lastUpdated} />
          <InternetConnectivity />
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


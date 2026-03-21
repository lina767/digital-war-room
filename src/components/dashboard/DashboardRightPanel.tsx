import { useState, useEffect } from "react";
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
import { AgentsStatusBar } from "@/components/dashboard/AgentsStatusBar";
import { LiveSocialMonitor } from "@/components/dashboard/LiveSocialMonitor";
import { CollapsiblePanel } from "@/components/dashboard/CollapsiblePanel";
import { CollapsibleDomainGroup } from "@/components/dashboard/CollapsibleDomainGroup";
import { CorroboratedPatternsBlock } from "@/components/dashboard/CorroboratedPatternsBlock";
import {
  FEED_VIEW_STORAGE_KEY,
  type FeedSectionId,
  type FeedDomainId,
  FEED_DOMAINS,
} from "@/components/dashboard/feedSectionConfig";
import type { ProximityEvidence } from "@/lib/proximityAnalyzerService";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { filterArticlesBySourceKeys } from "@/lib/headlineSources";
import { Link } from "react-router-dom";
import { DOCS_HOW_IT_WORKS_DASHBOARD_GUIDE, DOCS_SOURCE_DIRECTORY } from "@/lib/docLinks";
import { Target, X, Globe, LayoutGrid, List, Focus } from "lucide-react";
import { IntelPanelSkeleton } from "@/components/dashboard/IntelPanel";
import { FindingConfidenceBadge, normalizeFindingConfidence } from "@/components/dashboard/FindingConfidenceBadge";
import { formatTimeAgo } from "@/lib/utils";
import { useSocialWebSocket } from "@/hooks/useSocialWebSocket";

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
          <Target className="h-3.5 w-3.5" aria-hidden />
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

export type FeedViewMode = "full" | "summary" | "focus";

function loadFeedView(): FeedViewMode {
  try {
    const raw = localStorage.getItem(FEED_VIEW_STORAGE_KEY);
    if (raw === "summary" || raw === "focus" || raw === "full") return raw;
  } catch {
    // ignore
  }
  return "full";
}

function saveFeedView(mode: FeedViewMode) {
  try {
    localStorage.setItem(FEED_VIEW_STORAGE_KEY, String(mode));
  } catch {
    // ignore
  }
}

interface DashboardRightPanelProps {
  rightPanelOpen: boolean;
  setRightPanelOpen: (open: boolean) => void;
  conflictData: ConflictData | null;
  lastUpdated: Date | null;
  displayConflictLabel: string;
  activeConflict?: string | null;
  analysisLoading?: boolean;
  proximityEvidence: ProximityEvidence[];
  /** Empty = all headline sources. Shared with Live ticker. */
  headlineAllowedSources: Set<string>;
  onHeadlineAllowedSourcesChange: (next: Set<string>) => void;
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
  headlineAllowedSources,
  onHeadlineAllowedSourcesChange,
}: DashboardRightPanelProps) {
  const [feedView, setFeedView] = useState<FeedViewMode>(loadFeedView);
  const socialStream = useSocialWebSocket(activeConflict || displayConflictLabel || "Iran", true);

  useEffect(() => {
    saveFeedView(feedView);
  }, [feedView]);

  const domainOrder: FeedDomainId[] = ["information", "political", "security", "economic"];

  const renderFullFeed = () => (
    <>
      {domainOrder.map((domainId) => (
        <CollapsibleDomainGroup key={domainId} domainId={domainId}>
          {FEED_DOMAINS[domainId].sectionIds.map((sectionId) =>
            renderSection(sectionId as FeedSectionId)
          )}
        </CollapsibleDomainGroup>
      ))}
      {conflictData?.corroborated_patterns && conflictData.corroborated_patterns.length > 0 && (
        <div className="pt-2">
          <CorroboratedPatternsBlock patterns={conflictData.corroborated_patterns} />
        </div>
      )}
    </>
  );

  const renderSection = (sectionId: FeedSectionId) => {
    switch (sectionId) {
      case "briefing":
        return (
          <CollapsiblePanel
            key={sectionId}
            sectionId={sectionId}
            title="UPDATED BRIEFING"
            headerRight={<span className="text-[11px] text-muted-foreground">{formatTimeAgo(lastUpdated)}</span>}
          >
            <UpdatedBriefing data={conflictData} conflictLabel={displayConflictLabel} lastUpdated={lastUpdated} isLoading={analysisLoading} embedded />
          </CollapsiblePanel>
        );
      case "signal-framework":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="SIGNAL FRAMEWORK">
            <SignalFrameworkPanel data={conflictData} activeConflict={activeConflict} embedded />
          </CollapsiblePanel>
        );
      case "predictive":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="PREDICTIVE OUTLOOK">
            <PredictivePanel data={conflictData} embedded />
          </CollapsiblePanel>
        );
      case "compliance":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="SANCTIONS COMPLIANCE">
            <CompliancePanel data={conflictData} embedded />
          </CollapsiblePanel>
        );
      case "chokepoint":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="CHOKEPOINT MONITOR">
            <ChokePointPanel data={conflictData} embedded />
          </CollapsiblePanel>
        );
      case "global-impact":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="GLOBAL IMPACT">
            <GlobalImpactPanel data={conflictData} embedded />
          </CollapsiblePanel>
        );
      case "headlines": {
        const raw = conflictData?.news?.articles ?? [];
        const filtered = filterArticlesBySourceKeys(raw, headlineAllowedSources);
        return (
          <CollapsiblePanel
            key={sectionId}
            sectionId={sectionId}
            title="LATEST HEADLINES"
            headerRight={raw.length ? (
              <span className="text-[11px] text-muted-foreground">
                {filtered.length === raw.length ? `${raw.length} stories` : `${filtered.length}/${raw.length} stories`}
              </span>
            ) : undefined}
          >
            <LatestHeadlines
              data={conflictData}
              maxItems={5}
              embedded
              allowedSourceKeys={headlineAllowedSources}
              onAllowedSourceKeysChange={onHeadlineAllowedSourcesChange}
            />
          </CollapsiblePanel>
        );
      }
      case "events-timeline":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="EVENTS TIMELINE">
            <EventsTimeline data={conflictData} embedded />
          </CollapsiblePanel>
        );
      case "proximity":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="PROXIMITY ANALYZER">
            <ProximityAnalyzerBlock
              analysisLoading={analysisLoading}
              proximityEvidence={proximityEvidence}
              proximitySummary={conflictData?.proximity?.summary}
              reasonEmpty={conflictData?.proximity?.reason_empty}
              errorMessage={conflictData?.proximity?.error_message}
            />
          </CollapsiblePanel>
        );
      case "activity-connectivity":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="ACTIVITY & CONNECTIVITY">
            <div className="p-3 space-y-3">
              <GreyNoisePanel conflict={activeConflict || "Iran"} />
              <NewsSentiment newsScore={conflictData?.news?.news_score} lastUpdated={lastUpdated} />
              <InternetConnectivity />
              <FlightRadar sigint={conflictData?.sigint} />
              <PredictionMarkets polymarket={conflictData?.finint?.polymarket} fetchedAt={conflictData?.finint?.polymarket_fetched_at} polymarketHistory={conflictData?.finint?.polymarket_history} />
              <LiveSocialMonitor
                status={socialStream.status}
                error={socialStream.error}
                lastUpdated={socialStream.lastUpdated}
                twitter={socialStream.twitter}
                telegram={socialStream.telegram}
                reddit={socialStream.reddit}
              />
            </div>
          </CollapsiblePanel>
        );
      default:
        return null;
    }
  };

  const summaryLine = (label: string, value: string) => (
    <div key={label} className="flex items-center justify-between text-xs py-1 border-b border-border/60 last:border-0">
      <span className="text-muted-foreground font-mono">{label}</span>
      <span className="font-mono text-foreground">{value}</span>
    </div>
  );

  const renderSummaryView = () => {
    const keyFindings = conflictData?.key_findings ?? [];
    const riskLevel = conflictData?.compliance?.risk_score?.level ?? "—";
    const cpData = conflictData?.chokepoint;
    const chokepoints = cpData?.chokepoints ?? [];
    const restricted = chokepoints.filter((c) => (c.status ?? "").toUpperCase() !== "OPEN").length;
    const articles = conflictData?.news?.articles ?? [];
    const predictive = conflictData?.predictive?.escalation?.[0]?.level ?? conflictData?.predictive?.baseline_escalation?.level ?? "—";
    return (
      <div className="space-y-4">
        <UpdatedBriefing data={conflictData} conflictLabel={displayConflictLabel} lastUpdated={lastUpdated} isLoading={analysisLoading} />
        <div className="rounded-lg border border-border bg-card/40 p-3 space-y-2">
          <p className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">AT A GLANCE</p>
          {summaryLine("Compliance", riskLevel)}
          {summaryLine("ChokePoints", restricted > 0 ? `${restricted} restricted` : "All open")}
          {summaryLine("Headlines", `${articles.length} new`)}
          {summaryLine("Predictive", String(predictive))}
        </div>
        {keyFindings.length > 0 && (
          <div className="rounded-lg border border-border bg-card/40 p-3">
            <p className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">TOP FINDINGS</p>
            <ul className="space-y-1.5">
              {keyFindings.slice(0, 3).map((f, i) => (
                <li key={i} className="text-xs leading-relaxed flex gap-2 items-start">
                  <FindingConfidenceBadge level={normalizeFindingConfidence(conflictData?.key_findings_confidence?.[i])} />
                  <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-primary mt-1.5" />
                  <span className="min-w-0">{f}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  };

  const renderFocusView = () => {
    const summary = conflictData?.summary ?? null;
    const keyFindings = conflictData?.key_findings ?? [];
    const score = conflictData?.escalation_score ?? null;
    const threat = conflictData?.threat_level ?? "—";
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-border bg-card/40 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] text-muted-foreground">ESCALATION</span>
            <span className="font-mono text-lg font-bold text-primary">{score ?? "—"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] text-muted-foreground">THREAT</span>
            <span className="font-mono text-sm font-medium">{threat}</span>
          </div>
        </div>
        {summary && <p className="text-sm leading-relaxed">{summary}</p>}
        {keyFindings.length > 0 && (
          <div>
            <p className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">WHAT'S NEW</p>
            <ul className="space-y-1.5">
              {keyFindings.slice(0, 3).map((f, i) => (
                <li key={i} className="text-xs leading-relaxed flex gap-2 items-start">
                  <FindingConfidenceBadge level={normalizeFindingConfidence(conflictData?.key_findings_confidence?.[i])} />
                  <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-primary mt-1.5" />
                  <span className="min-w-0">{f}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  };

  return (
    <aside
      className={`
          ${rightPanelOpen ? "translate-x-0" : "translate-x-full"}
          md:translate-x-0
          w-[min(18rem,90vw)] sm:w-72 md:min-w-[380px] md:flex-[1_1_40%] md:min-w-0 border-l border-border flex-shrink-0 p-4 flex flex-col overflow-y-auto overscroll-contain bg-background
          absolute md:relative inset-y-0 right-0 z-20
          transition-transform duration-300 ease-in-out
        `}
      aria-label="Intelligence feed"
    >
      <div className="flex items-center justify-between mb-3 gap-2">
        <h2 className="font-mono text-xs text-muted-foreground tracking-wider truncate">INTELLIGENCE FEED</h2>
        <div className="flex items-center gap-0.5" role="group" aria-label="Feed layout">
          <button
            type="button"
            aria-label="Full view"
            aria-pressed={feedView === "full"}
            title="Full view"
            onClick={() => setFeedView("full")}
            className={`min-h-8 min-w-8 flex items-center justify-center rounded-md transition-colors ${
              feedView === "full" ? "bg-primary/20 text-primary" : "text-muted-foreground hover:bg-muted/50"
            }`}
          >
            <List className="h-3.5 w-3.5" aria-hidden />
          </button>
          <button
            type="button"
            aria-label="Summary view"
            aria-pressed={feedView === "summary"}
            title="Summary view"
            onClick={() => setFeedView("summary")}
            className={`min-h-8 min-w-8 flex items-center justify-center rounded-md transition-colors ${
              feedView === "summary" ? "bg-primary/20 text-primary" : "text-muted-foreground hover:bg-muted/50"
            }`}
          >
            <LayoutGrid className="h-3.5 w-3.5" aria-hidden />
          </button>
          <button
            type="button"
            aria-label="Focus view"
            aria-pressed={feedView === "focus"}
            title="Focus view"
            onClick={() => setFeedView("focus")}
            className={`min-h-8 min-w-8 flex items-center justify-center rounded-md transition-colors ${
              feedView === "focus" ? "bg-primary/20 text-primary" : "text-muted-foreground hover:bg-muted/50"
            }`}
          >
            <Focus className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
        <button
          type="button"
          aria-label="Close panel"
          className="md:hidden min-h-11 min-w-11 flex items-center justify-center -m-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 active:bg-muted touch-manipulation"
          onClick={() => setRightPanelOpen(false)}
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      <div className="mb-4 rounded-lg border border-border overflow-hidden bg-card/30">
        <div className="px-2 py-1.5 border-b border-border flex items-center gap-1.5">
          <Globe className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
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
        ) : feedView === "summary" ? (
          renderSummaryView()
        ) : feedView === "focus" ? (
          renderFocusView()
        ) : (
          renderFullFeed()
        )}
      </div>

      <div className="mt-4 pt-3 border-t border-border">
        <AgentsStatusBar />
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">
        <Link to={DOCS_HOW_IT_WORKS_DASHBOARD_GUIDE} className="text-primary hover:underline">How to read the dashboard</Link>
        {" · "}
        <Link to="/blog" className="text-primary hover:underline">Blog</Link>
        {" · "}
        <Link to={DOCS_SOURCE_DIRECTORY} className="text-primary hover:underline">Source Directory</Link>
        {" · "}
        <Link to="/app/monitoring" className="text-primary hover:underline">Agent Monitor</Link>
      </p>
    </aside>
  );
}

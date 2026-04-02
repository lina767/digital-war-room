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
import { ErrorBoundary } from "@/components/ErrorBoundary";
import {
  FEED_VIEW_STORAGE_KEY,
  type FeedSectionId,
  type FeedDomainId,
  FEED_DOMAINS,
} from "@/components/dashboard/feedSectionConfig";
import type { ProximityEvidence } from "@/lib/proximityAnalyzerService";
import type { ConflictData } from "@/types/conflict";
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

type PizzaBand = "LOW" | "MEDIUM" | "HIGH";

function getPizzaBand(score: number | null | undefined): PizzaBand | null {
  if (typeof score !== "number" || !Number.isFinite(score)) return null;
  if (score >= 67) return "HIGH";
  if (score >= 34) return "MEDIUM";
  return "LOW";
}

function getPizzaBandClass(band: PizzaBand | null): string {
  if (band === "HIGH") return "bg-destructive/15 text-destructive border-destructive/40";
  if (band === "MEDIUM") return "bg-amber-500/15 text-amber-300 border-amber-500/35";
  if (band === "LOW") return "bg-emerald-500/15 text-emerald-300 border-emerald-500/35";
  return "bg-muted/20 text-muted-foreground border-border/50";
}

function isLebanonFocus(activeConflict: string | null | undefined): boolean {
  return (activeConflict ?? "").trim().toLowerCase() === "lebanon";
}

function isRedSeaFocus(activeConflict: string | null | undefined): boolean {
  return (activeConflict ?? "").trim().toLowerCase() === "red sea";
}

function isIranFocus(activeConflict: string | null | undefined): boolean {
  return (activeConflict ?? "").trim().toLowerCase() === "iran";
}

function isMiddleEastFocus(activeConflict: string | null | undefined): boolean {
  return (activeConflict ?? "").trim().toLowerCase() === "middle east";
}

function getLebanonFocusHighlights(conflictData: ConflictData | null): string[] {
  if (!conflictData) return [];
  const highlights: string[] = [];
  const findings = conflictData.key_findings ?? [];
  const articles = conflictData.news?.articles ?? [];
  const articleTitles = articles
    .map((a) => String(a?.title ?? "").toLowerCase())
    .filter(Boolean);
  const findingText = findings.map((f) => String(f).toLowerCase());
  const combined = [...articleTitles, ...findingText];

  const hasAny = (terms: string[]) => combined.some((txt) => terms.some((t) => txt.includes(t)));

  if (hasAny(["south lebanon", "blue line", "israel lebanon", "israel-lebanon", "litani", "border"])) {
    highlights.push("Border activity around South Lebanon / Blue Line remains elevated.");
  }
  if (hasAny(["hezbollah", "hizbullah"])) {
    highlights.push("Hezbollah-linked activity is present in current signal flow.");
  }
  if (hasAny(["beirut", "tyre", "nabatieh"])) {
    highlights.push("Location-specific reporting includes Beirut / Tyre / Nabatieh references.");
  }
  if (hasAny(["unifil"])) {
    highlights.push("UNIFIL is part of the reporting picture and should be monitored.");
  }
  if (hasAny(["ceasefire", "de-escalat", "deescalat", "talks"])) {
    highlights.push("Diplomatic de-escalation signals are visible in parallel to security updates.");
  }

  return highlights.slice(0, 3);
}

function getIranFocusHighlights(conflictData: ConflictData | null): string[] {
  if (!conflictData) return [];
  const highlights: string[] = [];
  const findings = conflictData.key_findings ?? [];
  const articles = conflictData.news?.articles ?? [];
  const articleTitles = articles.map((a) => String(a?.title ?? "").toLowerCase()).filter(Boolean);
  const findingText = findings.map((f) => String(f).toLowerCase());
  const combined = [...articleTitles, ...findingText];
  const hasAny = (terms: string[]) => combined.some((txt) => terms.some((t) => txt.includes(t)));

  if (hasAny(["iran", "tehran", "irgc", "khamenei"])) {
    highlights.push("Iran core-state signaling remains active across current reporting.");
  }
  if (hasAny(["hormuz", "strait of hormuz", "persian gulf"])) {
    highlights.push("Hormuz/Persian Gulf chokepoint pressure is part of the threat picture.");
  }
  if (hasAny(["nuclear", "iaea"])) {
    highlights.push("Nuclear/IAEA-linked narratives are visible in this cycle.");
  }
  if (hasAny(["sanctions", "ofac"])) {
    highlights.push("Sanctions and enforcement signals remain relevant for escalation context.");
  }
  if (hasAny(["ceasefire", "talks", "de-escalat", "deescalat"])) {
    highlights.push("De-escalation messaging appears, but coexists with hard-security signals.");
  }

  return highlights.slice(0, 3);
}

function getRedSeaFocusHighlights(conflictData: ConflictData | null): string[] {
  if (!conflictData) return [];
  const highlights: string[] = [];
  const findings = conflictData.key_findings ?? [];
  const articles = conflictData.news?.articles ?? [];
  const articleTitles = articles.map((a) => String(a?.title ?? "").toLowerCase()).filter(Boolean);
  const findingText = findings.map((f) => String(f).toLowerCase());
  const combined = [...articleTitles, ...findingText];
  const hasAny = (terms: string[]) => combined.some((txt) => terms.some((t) => txt.includes(t)));

  if (hasAny(["houthi", "houthis", "ansarallah"])) {
    highlights.push("Houthi-linked activity remains a primary driver in this theater.");
  }
  if (hasAny(["red sea", "bab el-mandeb", "bab al-mandab", "gulf of aden"])) {
    highlights.push("Red Sea / Bab el-Mandeb maritime pressure is visible in current reporting.");
  }
  if (hasAny(["shipping", "vessel", "merchant", "tanker", "container", "suez"])) {
    highlights.push("Commercial shipping risk and rerouting pressure are part of the active signal set.");
  }
  if (hasAny(["missile", "drone", "strike", "intercept"])) {
    highlights.push("Strike and interception indicators suggest sustained kinetic tempo.");
  }
  if (hasAny(["ceasefire", "talks", "de-escalat", "deescalat"])) {
    highlights.push("Parallel de-escalation messaging appears alongside kinetic indicators.");
  }

  return highlights.slice(0, 3);
}

function getRedSeaFocusKpis(conflictData: ConflictData | null): {
  shipping: number;
  strikes: number;
  houthi: number;
} {
  if (!conflictData) return { shipping: 0, strikes: 0, houthi: 0 };
  const findings = conflictData.key_findings ?? [];
  const articles = conflictData.news?.articles ?? [];
  const combined = [
    ...articles.map((a) => `${String(a?.title ?? "")} ${String(a?.description ?? "")}`.toLowerCase()),
    ...findings.map((f) => String(f).toLowerCase()),
  ];
  const countMatches = (terms: string[]) =>
    combined.reduce((acc, txt) => (terms.some((t) => txt.includes(t)) ? acc + 1 : acc), 0);

  return {
    shipping: countMatches(["shipping", "vessel", "merchant", "container", "tanker", "suez", "maritime"]),
    strikes: countMatches(["strike", "missile", "drone", "attack", "intercept", "interception"]),
    houthi: countMatches(["houthi", "houthis", "ansarallah"]),
  };
}

interface DashboardRightPanelProps {
  rightPanelOpen: boolean;
  setRightPanelOpen: (open: boolean) => void;
  conflictData: ConflictData | null;
  lastUpdated: Date | null;
  displayConflictLabel: string;
  activeConflict?: string | null;
  analysisLoading?: boolean;
  analysisRunning?: boolean;
  analysisError?: string | null;
  onRunAnalysis?: () => void | Promise<unknown>;
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
  analysisRunning,
  analysisError,
  onRunAnalysis,
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
            <ErrorBoundary sectionLabel="Updated Briefing">
              <UpdatedBriefing
                data={conflictData}
                conflictLabel={displayConflictLabel}
                lastUpdated={lastUpdated}
                isLoading={analysisLoading}
                isRunning={analysisRunning}
                analysisError={analysisError}
                onRunAnalysis={onRunAnalysis}
                embedded
              />
            </ErrorBoundary>
          </CollapsiblePanel>
        );
      case "signal-framework":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="SIGNAL FRAMEWORK">
            <ErrorBoundary sectionLabel="Signal Framework">
              <SignalFrameworkPanel data={conflictData} activeConflict={activeConflict} embedded />
            </ErrorBoundary>
          </CollapsiblePanel>
        );
      case "predictive":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="PREDICTIVE OUTLOOK">
            <ErrorBoundary sectionLabel="Predictive Outlook">
              <PredictivePanel data={conflictData} embedded />
            </ErrorBoundary>
          </CollapsiblePanel>
        );
      case "compliance":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="SANCTIONS COMPLIANCE">
            <ErrorBoundary sectionLabel="Sanctions Compliance">
              <CompliancePanel data={conflictData} embedded />
            </ErrorBoundary>
          </CollapsiblePanel>
        );
      case "chokepoint":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="CHOKEPOINT MONITOR">
            <ErrorBoundary sectionLabel="Chokepoint Monitor">
              <ChokePointPanel data={conflictData} embedded />
            </ErrorBoundary>
          </CollapsiblePanel>
        );
      case "global-impact":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="GLOBAL IMPACT">
            <ErrorBoundary sectionLabel="Global Impact">
              <GlobalImpactPanel data={conflictData} embedded />
            </ErrorBoundary>
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
            <ErrorBoundary sectionLabel="Latest Headlines">
              <LatestHeadlines
                data={conflictData}
                maxItems={5}
                embedded
                allowedSourceKeys={headlineAllowedSources}
                onAllowedSourceKeysChange={onHeadlineAllowedSourcesChange}
              />
            </ErrorBoundary>
          </CollapsiblePanel>
        );
      }
      case "events-timeline":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="EVENTS TIMELINE">
            <ErrorBoundary sectionLabel="Events Timeline">
              <EventsTimeline data={conflictData} embedded />
            </ErrorBoundary>
          </CollapsiblePanel>
        );
      case "proximity":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="PROXIMITY ANALYZER">
            <ErrorBoundary sectionLabel="Proximity Analyzer">
              <ProximityAnalyzerBlock
                analysisLoading={analysisLoading}
                proximityEvidence={proximityEvidence}
                proximitySummary={conflictData?.proximity?.summary}
                reasonEmpty={conflictData?.proximity?.reason_empty}
                errorMessage={conflictData?.proximity?.error_message}
              />
            </ErrorBoundary>
          </CollapsiblePanel>
        );
      case "activity-connectivity":
        return (
          <CollapsiblePanel key={sectionId} sectionId={sectionId} title="ACTIVITY & CONNECTIVITY">
            <div className="p-3 space-y-3">
              <ErrorBoundary sectionLabel="GreyNoise Panel">
                <GreyNoisePanel conflict={activeConflict || "Iran"} />
              </ErrorBoundary>
              <ErrorBoundary sectionLabel="News Sentiment">
                <NewsSentiment newsScore={conflictData?.news?.news_score} lastUpdated={lastUpdated} />
              </ErrorBoundary>
              <ErrorBoundary sectionLabel="Internet Connectivity">
                <InternetConnectivity />
              </ErrorBoundary>
              <ErrorBoundary sectionLabel="FlightRadar">
                <FlightRadar
                  sigint={conflictData?.sigint as unknown as Parameters<typeof FlightRadar>[0]["sigint"]}
                />
              </ErrorBoundary>
              <ErrorBoundary sectionLabel="Prediction Markets">
                <PredictionMarkets polymarket={conflictData?.finint?.polymarket} fetchedAt={conflictData?.finint?.polymarket_fetched_at} polymarketHistory={conflictData?.finint?.polymarket_history} />
              </ErrorBoundary>
              <ErrorBoundary sectionLabel="Live Social Monitor">
                <LiveSocialMonitor
                  status={socialStream.status}
                  error={socialStream.error}
                  lastUpdated={socialStream.lastUpdated}
                  twitter={socialStream.twitter}
                  telegram={socialStream.telegram}
                  reddit={socialStream.reddit}
                />
              </ErrorBoundary>
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
    const riskLevel = conflictData?.compliance?.risk_score?.level ?? "–";
    const cpData = conflictData?.chokepoint;
    const chokepoints = cpData?.chokepoints ?? [];
    const restricted = chokepoints.filter((c) => String(c.status ?? "").toUpperCase() !== "OPEN").length;
    const articles = conflictData?.news?.articles ?? [];
    const predictive = conflictData?.predictive?.escalation?.[0]?.level ?? conflictData?.predictive?.baseline_escalation?.level ?? "–";
    const pentagonScore = conflictData?.pentagon?.pentagon_score;
    const pentagonDisplay = typeof pentagonScore === "number" ? Math.round(pentagonScore).toString() : "–";
    const pizzaBand = getPizzaBand(pentagonScore);
    const pizzaLabel = pizzaBand ? `${pentagonDisplay} (${pizzaBand})` : pentagonDisplay;
    return (
      <div className="space-y-4">
        <UpdatedBriefing
          data={conflictData}
          conflictLabel={displayConflictLabel}
          lastUpdated={lastUpdated}
          isLoading={analysisLoading}
          isRunning={analysisRunning}
          analysisError={analysisError}
          onRunAnalysis={onRunAnalysis}
        />
        <div className="rounded-lg border border-border bg-card/40 p-3 space-y-2">
          <p className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">AT A GLANCE</p>
          {summaryLine("Compliance", riskLevel)}
          {summaryLine("ChokePoints", restricted > 0 ? `${restricted} restricted` : "All open")}
          {summaryLine("Headlines", `${articles.length} new`)}
          {summaryLine("Pizza Index", pizzaLabel)}
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
    const threat = conflictData?.threat_level ?? "–";
    const pentagonScore = conflictData?.pentagon?.pentagon_score;
    const pizzaBand = getPizzaBand(pentagonScore);
    const lebanonMode = isLebanonFocus(activeConflict);
  const iranMode = isIranFocus(activeConflict);
    const redSeaMode = isRedSeaFocus(activeConflict);
  const middleEastMode = isMiddleEastFocus(activeConflict);
  const showLebanonFocus = lebanonMode || middleEastMode;
  const showIranFocus = iranMode || middleEastMode;
  const showRedSeaFocus = redSeaMode || middleEastMode;
    const lebanonHighlights = getLebanonFocusHighlights(conflictData);
  const iranHighlights = getIranFocusHighlights(conflictData);
    const redSeaHighlights = getRedSeaFocusHighlights(conflictData);
    const redSeaKpis = getRedSeaFocusKpis(conflictData);
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-border bg-card/40 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] text-muted-foreground">ESCALATION</span>
            <span className="font-mono text-lg font-bold text-primary">{score ?? "–"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] text-muted-foreground">THREAT</span>
            <span className="font-mono text-sm font-medium">{threat}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] text-muted-foreground">PIZZA INDEX</span>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-medium">{typeof pentagonScore === "number" ? Math.round(pentagonScore) : "–"}</span>
              <span
                className={`rounded border px-1.5 py-0.5 text-[10px] font-mono tracking-wide ${getPizzaBandClass(pizzaBand)}`}
                title="Informal proxy signal only; not a confirmed military indicator"
              >
                {pizzaBand ?? "N/A"}
              </span>
            </div>
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
        {showIranFocus && (
          <div className="rounded-lg border border-border bg-card/40 p-3">
            <p className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">IRAN FOCUS</p>
            {iranHighlights.length > 0 ? (
              <ul className="space-y-1.5">
                {iranHighlights.map((line, i) => (
                  <li key={`${line}-${i}`} className="text-xs leading-relaxed flex gap-2 items-start">
                    <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-primary mt-1.5" />
                    <span className="min-w-0">{line}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">
                No dedicated Iran-specific signals found yet in this cycle. Trigger a new run to refresh focused inputs.
              </p>
            )}
          </div>
        )}
        {showLebanonFocus && (
          <div className="rounded-lg border border-border bg-card/40 p-3">
            <p className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">LEBANON FOCUS</p>
            {lebanonHighlights.length > 0 ? (
              <ul className="space-y-1.5">
                {lebanonHighlights.map((line, i) => (
                  <li key={`${line}-${i}`} className="text-xs leading-relaxed flex gap-2 items-start">
                    <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-primary mt-1.5" />
                    <span className="min-w-0">{line}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">
                No dedicated Lebanon-specific signals found yet in this cycle. Trigger a new run to refresh focused inputs.
              </p>
            )}
          </div>
        )}
        {showRedSeaFocus && (
          <div className="rounded-lg border border-border bg-card/40 p-3">
            <p className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">RED SEA / HOUTHI FOCUS</p>
            <div className="mb-2 grid grid-cols-3 gap-2">
              <div className="rounded border border-border/70 bg-background/40 px-2 py-1">
                <div className="text-[10px] font-mono text-muted-foreground">Shipping</div>
                <div className="text-xs font-mono text-foreground">{redSeaKpis.shipping}</div>
              </div>
              <div className="rounded border border-border/70 bg-background/40 px-2 py-1">
                <div className="text-[10px] font-mono text-muted-foreground">Strikes</div>
                <div className="text-xs font-mono text-foreground">{redSeaKpis.strikes}</div>
              </div>
              <div className="rounded border border-border/70 bg-background/40 px-2 py-1">
                <div className="text-[10px] font-mono text-muted-foreground">Houthi</div>
                <div className="text-xs font-mono text-foreground">{redSeaKpis.houthi}</div>
              </div>
            </div>
            {redSeaHighlights.length > 0 ? (
              <ul className="space-y-1.5">
                {redSeaHighlights.map((line, i) => (
                  <li key={`${line}-${i}`} className="text-xs leading-relaxed flex gap-2 items-start">
                    <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-primary mt-1.5" />
                    <span className="min-w-0">{line}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">
                No dedicated Red Sea / Houthi signals found yet in this cycle. Trigger a new run to refresh focused inputs.
              </p>
            )}
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
            className={`min-h-8 min-w-8 max-lg:min-h-11 max-lg:min-w-11 flex items-center justify-center rounded-md transition-colors touch-manipulation ${
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
            className={`min-h-8 min-w-8 max-lg:min-h-11 max-lg:min-w-11 flex items-center justify-center rounded-md transition-colors touch-manipulation ${
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
            className={`min-h-8 min-w-8 max-lg:min-h-11 max-lg:min-w-11 flex items-center justify-center rounded-md transition-colors touch-manipulation ${
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
          <ErrorBoundary sectionLabel="World Overview Map">
            <WorldMap />
          </ErrorBoundary>
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
          <ErrorBoundary sectionLabel="Summary Feed">
            {renderSummaryView()}
          </ErrorBoundary>
        ) : feedView === "focus" ? (
          <ErrorBoundary sectionLabel="Focus Feed">
            {renderFocusView()}
          </ErrorBoundary>
        ) : (
          <ErrorBoundary sectionLabel="Full Feed">
            {renderFullFeed()}
          </ErrorBoundary>
        )}
      </div>

      <div className="mt-4 pt-3 border-t border-border">
        <ErrorBoundary sectionLabel="Agents Status Bar">
          <AgentsStatusBar />
        </ErrorBoundary>
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

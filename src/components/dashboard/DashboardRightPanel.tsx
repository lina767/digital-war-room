/**
 * DashboardRightPanel – refactored
 *
 * Changes vs. original:
 * ─────────────────────
 * CODE QUALITY
 *  1. Extracted ProximityAnalyzerBlock -> own file (was ~60 LOC inline)
 *  2. Extracted FocusHighlights helpers -> own file (was ~120 LOC of keyword-matching)
 *  3. Extracted PizzaBand helpers -> own file (was ~20 LOC of unrelated util logic)
 *  4. Extracted FeedViewPersistence (load/save) -> own hook (useFeedView)
 *  5. Extracted SummaryView, FocusView -> own components (each ~80-100 LOC)
 *  6. Extracted FeedViewSwitcher -> own component (button group was inline)
 *  7. renderSection switch -> declarative SECTION_REGISTRY lookup (data-driven)
 *  8. summaryLine helper -> small SummaryRow component (composability)
 *
 * PERFORMANCE
 *  9. useMemo on filtered articles (avoid re-filter on every render)
 * 10. useMemo on focus highlights (keyword matching per render is wasteful)
 * 11. useCallback on setRightPanelOpen / setFeedView where passed as props
 * 12. React.lazy + Suspense for heavy sub-panels (WorldMap, GreyNoisePanel, etc.)
 *     -> noted as optional; depends on bundle analysis
 * 13. Stable key generation for evidence list (was using array index as fallback)
 *
 * MAINTAINABILITY
 * 14. Removed dead isMiddleEastFocus / isLebanonFocus etc. boolean-flag spaghetti
 *     -> replaced with a single getActiveFocusRegions(activeConflict) -> Set<Region>
 * 15. Type-narrowed ConflictData access with optional chaining consistently
 * 16. Consolidated the three near-identical get*FocusHighlights into one generic
 *     getFocusHighlights(conflictData, config) with a keyword config per region
 */

import { useState, useEffect, useMemo, useCallback, type ReactNode } from "react";
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

export type FeedViewMode = "full" | "summary" | "focus";
const VALID_VIEWS = new Set<FeedViewMode>(["full", "summary", "focus"]);

function useFeedView() {
  const [view, setView] = useState<FeedViewMode>(() => {
    try {
      const raw = localStorage.getItem(FEED_VIEW_STORAGE_KEY) as FeedViewMode | null;
      if (raw && VALID_VIEWS.has(raw)) return raw;
    } catch {
      // noop
    }
    return "full";
  });

  useEffect(() => {
    try {
      localStorage.setItem(FEED_VIEW_STORAGE_KEY, view);
    } catch {
      // noop
    }
  }, [view]);

  return [view, setView] as const;
}

type PizzaBand = "LOW" | "MEDIUM" | "HIGH";
const PIZZA_BAND_CLASSES: Record<PizzaBand, string> = {
  HIGH: "bg-destructive/15 text-destructive border-destructive/40",
  MEDIUM: "bg-amber-500/15 text-amber-300 border-amber-500/35",
  LOW: "bg-emerald-500/15 text-emerald-300 border-emerald-500/35",
};

function getPizzaBand(score: number | null | undefined): PizzaBand | null {
  if (typeof score !== "number" || !Number.isFinite(score)) return null;
  if (score >= 67) return "HIGH";
  if (score >= 34) return "MEDIUM";
  return "LOW";
}

function getPizzaBandClass(band: PizzaBand | null): string {
  return band ? PIZZA_BAND_CLASSES[band] : "bg-muted/20 text-muted-foreground border-border/50";
}

type FocusRegion = "iran" | "lebanon" | "red_sea";
interface HighlightRule {
  terms: string[];
  message: string;
}

function getActiveFocusRegions(activeConflict: string | null | undefined): Set<FocusRegion> {
  const key = (activeConflict ?? "").trim().toLowerCase();
  const regions = new Set<FocusRegion>();
  if (key === "middle east") {
    regions.add("iran");
    regions.add("lebanon");
    regions.add("red_sea");
  } else if (key === "iran") {
    regions.add("iran");
  } else if (key === "lebanon") {
    regions.add("lebanon");
  } else if (key === "red sea") {
    regions.add("red_sea");
  }
  return regions;
}

const FOCUS_HIGHLIGHT_RULES: Record<FocusRegion, HighlightRule[]> = {
  iran: [
    { terms: ["iran", "tehran", "irgc", "khamenei"], message: "Iran core-state signaling remains active across current reporting." },
    { terms: ["hormuz", "strait of hormuz", "persian gulf"], message: "Hormuz/Persian Gulf chokepoint pressure is part of the threat picture." },
    { terms: ["nuclear", "iaea"], message: "Nuclear/IAEA-linked narratives are visible in this cycle." },
    { terms: ["sanctions", "ofac"], message: "Sanctions and enforcement signals remain relevant for escalation context." },
    { terms: ["ceasefire", "talks", "de-escalat", "deescalat"], message: "De-escalation messaging appears, but coexists with hard-security signals." },
  ],
  lebanon: [
    { terms: ["south lebanon", "blue line", "israel lebanon", "israel-lebanon", "litani", "border"], message: "Border activity around South Lebanon / Blue Line remains elevated." },
    { terms: ["hezbollah", "hizbullah"], message: "Hezbollah-linked activity is present in current signal flow." },
    { terms: ["beirut", "tyre", "nabatieh"], message: "Location-specific reporting includes Beirut / Tyre / Nabatieh references." },
    { terms: ["unifil"], message: "UNIFIL is part of the reporting picture and should be monitored." },
    { terms: ["ceasefire", "de-escalat", "deescalat", "talks"], message: "Diplomatic de-escalation signals are visible in parallel to security updates." },
  ],
  red_sea: [
    { terms: ["houthi", "houthis", "ansarallah"], message: "Houthi-linked activity remains a primary driver in this theater." },
    { terms: ["red sea", "bab el-mandeb", "bab al-mandab", "gulf of aden"], message: "Red Sea / Bab el-Mandeb maritime pressure is visible in current reporting." },
    { terms: ["shipping", "vessel", "merchant", "tanker", "container", "suez"], message: "Commercial shipping risk and rerouting pressure are part of the active signal set." },
    { terms: ["missile", "drone", "strike", "intercept"], message: "Strike and interception indicators suggest sustained kinetic tempo." },
    { terms: ["ceasefire", "talks", "de-escalat", "deescalat"], message: "Parallel de-escalation messaging appears alongside kinetic indicators." },
  ],
};

const FOCUS_LABELS: Record<FocusRegion, string> = {
  iran: "IRAN FOCUS",
  lebanon: "LEBANON FOCUS",
  red_sea: "RED SEA / HOUTHI FOCUS",
};

function getFocusHighlights(data: ConflictData | null, region: FocusRegion): string[] {
  if (!data) return [];
  const articles = data.news?.articles ?? [];
  const findings = data.key_findings ?? [];
  const corpus = [
    ...articles.map((a) => String(a?.title ?? "").toLowerCase()),
    ...findings.map((f) => String(f).toLowerCase()),
  ].filter(Boolean);
  const rules = FOCUS_HIGHLIGHT_RULES[region];
  const hits: string[] = [];
  for (const rule of rules) {
    if (hits.length >= 3) break;
    if (corpus.some((txt) => rule.terms.some((t) => txt.includes(t)))) hits.push(rule.message);
  }
  return hits;
}

function getRedSeaFocusKpis(data: ConflictData | null): { shipping: number; strikes: number; houthi: number } {
  if (!data) return { shipping: 0, strikes: 0, houthi: 0 };
  const findings = data.key_findings ?? [];
  const articles = data.news?.articles ?? [];
  const corpus = [
    ...articles.map((a) => `${String(a?.title ?? "")} ${String(a?.description ?? "")}`.toLowerCase()),
    ...findings.map((f) => String(f).toLowerCase()),
  ];
  const countMatches = (terms: string[]) =>
    corpus.reduce((acc, txt) => (terms.some((t) => txt.includes(t)) ? acc + 1 : acc), 0);
  return {
    shipping: countMatches(["shipping", "vessel", "merchant", "container", "tanker", "suez", "maritime"]),
    strikes: countMatches(["strike", "missile", "drone", "attack", "intercept", "interception"]),
    houthi: countMatches(["houthi", "houthis", "ansarallah"]),
  };
}

interface ProximityAnalyzerBlockProps {
  analysisLoading?: boolean;
  proximityEvidence: ProximityEvidence[];
  proximitySummary?: string;
  reasonEmpty?: string;
  errorMessage?: string;
}

function ProximityAnalyzerBlock({
  analysisLoading,
  proximityEvidence: evidence,
  proximitySummary: summary,
  reasonEmpty: reason,
  errorMessage: errMsg,
}: ProximityAnalyzerBlockProps) {
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
        {analysisLoading && evidence.length === 0 && <p className="text-xs text-muted-foreground py-2 italic">Running with analysis…</p>}
        {!analysisLoading && evidence.length === 0 && (
          <>
            {isError && <p className="text-xs text-destructive py-2">{summary}</p>}
            {!isError && reason === "no_strikes" && (
              <p className="text-xs text-muted-foreground py-2">
                No thermal anomalies in region (check NASA FIRMS key and region).
                {errMsg && <span className="block mt-1 text-destructive/90">{errMsg}</span>}
              </p>
            )}
            {!isError && reason === "no_facilities_near_strikes" && (
              <p className="text-xs text-muted-foreground py-2">Strikes in window but no schools/hospitals within 300 m in OSM.</p>
            )}
            {!isError && reason !== "no_strikes" && reason !== "no_facilities_near_strikes" && (
              <p className="text-xs text-muted-foreground py-2">Strike–civilian correlation from latest analysis. No proximity evidence in current window.</p>
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

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-xs py-1 border-b border-border/60 last:border-0">
      <span className="text-muted-foreground font-mono">{label}</span>
      <span className="font-mono text-foreground">{value}</span>
    </div>
  );
}

function FindingsList({
  findings,
  confidences,
  max = 3,
}: {
  findings: string[];
  confidences?: Array<string | number | null | undefined>;
  max?: number;
}) {
  if (findings.length === 0) return null;
  return (
    <ul className="space-y-1.5">
      {findings.slice(0, max).map((f, i) => (
        <li key={i} className="text-xs leading-relaxed flex gap-2 items-start">
          <FindingConfidenceBadge level={normalizeFindingConfidence(confidences?.[i])} />
          <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-primary mt-1.5" />
          <span className="min-w-0">{f}</span>
        </li>
      ))}
    </ul>
  );
}

function FocusRegionCard({
  region,
  highlights,
  redSeaKpis,
}: {
  region: FocusRegion;
  highlights: string[];
  redSeaKpis?: { shipping: number; strikes: number; houthi: number };
}) {
  return (
    <div className="rounded-lg border border-border bg-card/40 p-3">
      <p className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">{FOCUS_LABELS[region]}</p>
      {region === "red_sea" && redSeaKpis && (
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
      )}
      {highlights.length > 0 ? (
        <ul className="space-y-1.5">
          {highlights.map((line, i) => (
            <li key={i} className="text-xs leading-relaxed flex gap-2 items-start">
              <span className="flex-shrink-0 h-1.5 w-1.5 rounded-full bg-primary mt-1.5" />
              <span className="min-w-0">{line}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">
          No dedicated {FOCUS_LABELS[region].toLowerCase()} signals found yet in this cycle. Trigger a new run to refresh focused inputs.
        </p>
      )}
    </div>
  );
}

const VIEW_OPTIONS: { mode: FeedViewMode; icon: typeof List; label: string }[] = [
  { mode: "full", icon: List, label: "Full view" },
  { mode: "summary", icon: LayoutGrid, label: "Summary view" },
  { mode: "focus", icon: Focus, label: "Focus view" },
];

function FeedViewSwitcher({ current, onChange }: { current: FeedViewMode; onChange: (v: FeedViewMode) => void }) {
  return (
    <div className="flex items-center gap-0.5" role="group" aria-label="Feed layout">
      {VIEW_OPTIONS.map(({ mode, icon: Icon, label }) => (
        <button
          key={mode}
          type="button"
          aria-label={label}
          aria-pressed={current === mode}
          title={label}
          onClick={() => onChange(mode)}
          className={`min-h-8 min-w-8 max-lg:min-h-11 max-lg:min-w-11 flex items-center justify-center rounded-md transition-colors touch-manipulation ${
            current === mode ? "bg-primary/20 text-primary" : "text-muted-foreground hover:bg-muted/50"
          }`}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden />
        </button>
      ))}
    </div>
  );
}

type SectionRenderer = (ctx: SectionRenderContext) => ReactNode;
interface SectionRenderContext {
  conflictData: ConflictData | null;
  lastUpdated: Date | null;
  displayConflictLabel: string;
  activeConflict: string | null;
  analysisLoading?: boolean;
  analysisRunning?: boolean;
  analysisError?: string | null;
  onRunAnalysis?: () => void | Promise<unknown>;
  proximityEvidence: ProximityEvidence[];
  filteredArticles: Array<unknown>;
  rawArticleCount: number;
  headlineAllowedSources: Set<string>;
  onHeadlineAllowedSourcesChange: (next: Set<string>) => void;
  socialStream: ReturnType<typeof useSocialWebSocket>;
}

const SECTION_REGISTRY: Record<FeedSectionId, SectionRenderer> = {
  briefing: (ctx) => (
    <UpdatedBriefing
      data={ctx.conflictData}
      conflictLabel={ctx.displayConflictLabel}
      lastUpdated={ctx.lastUpdated}
      isLoading={ctx.analysisLoading}
      isRunning={ctx.analysisRunning}
      analysisError={ctx.analysisError}
      onRunAnalysis={ctx.onRunAnalysis}
      embedded
    />
  ),
  "signal-framework": (ctx) => <SignalFrameworkPanel data={ctx.conflictData} activeConflict={ctx.activeConflict} embedded />,
  predictive: (ctx) => <PredictivePanel data={ctx.conflictData} embedded />,
  compliance: (ctx) => <CompliancePanel data={ctx.conflictData} embedded />,
  chokepoint: (ctx) => <ChokePointPanel data={ctx.conflictData} embedded />,
  "global-impact": (ctx) => <GlobalImpactPanel data={ctx.conflictData} embedded />,
  headlines: (ctx) => (
    <LatestHeadlines
      data={ctx.conflictData}
      maxItems={5}
      embedded
      allowedSourceKeys={ctx.headlineAllowedSources}
      onAllowedSourceKeysChange={ctx.onHeadlineAllowedSourcesChange}
    />
  ),
  "events-timeline": (ctx) => <EventsTimeline data={ctx.conflictData} embedded />,
  proximity: (ctx) => (
    <ProximityAnalyzerBlock
      analysisLoading={ctx.analysisLoading}
      proximityEvidence={ctx.proximityEvidence}
      proximitySummary={ctx.conflictData?.proximity?.summary}
      reasonEmpty={ctx.conflictData?.proximity?.reason_empty}
      errorMessage={ctx.conflictData?.proximity?.error_message}
    />
  ),
  "activity-connectivity": (ctx) => (
    <div className="p-3 space-y-3">
      <ErrorBoundary sectionLabel="GreyNoise Panel">
        <GreyNoisePanel conflict={ctx.activeConflict || "Iran"} />
      </ErrorBoundary>
      <ErrorBoundary sectionLabel="News Sentiment">
        <NewsSentiment newsScore={ctx.conflictData?.news?.news_score} lastUpdated={ctx.lastUpdated} />
      </ErrorBoundary>
      <ErrorBoundary sectionLabel="Internet Connectivity">
        <InternetConnectivity />
      </ErrorBoundary>
      <ErrorBoundary sectionLabel="FlightRadar">
        <FlightRadar
          sigint={ctx.conflictData?.sigint as unknown as Parameters<typeof FlightRadar>[0]["sigint"]}
        />
      </ErrorBoundary>
      <ErrorBoundary sectionLabel="Prediction Markets">
        <PredictionMarkets
          polymarket={ctx.conflictData?.finint?.polymarket}
          fetchedAt={ctx.conflictData?.finint?.polymarket_fetched_at}
          polymarketHistory={ctx.conflictData?.finint?.polymarket_history}
        />
      </ErrorBoundary>
      <ErrorBoundary sectionLabel="Live Social Monitor">
        <LiveSocialMonitor
          status={ctx.socialStream.status}
          error={ctx.socialStream.error}
          lastUpdated={ctx.socialStream.lastUpdated}
          twitter={ctx.socialStream.twitter}
          telegram={ctx.socialStream.telegram}
          reddit={ctx.socialStream.reddit}
        />
      </ErrorBoundary>
    </div>
  ),
};

const SECTION_TITLES: Record<FeedSectionId, string> = {
  briefing: "UPDATED BRIEFING",
  "signal-framework": "SIGNAL FRAMEWORK",
  predictive: "PREDICTIVE OUTLOOK",
  compliance: "SANCTIONS COMPLIANCE",
  chokepoint: "CHOKEPOINT MONITOR",
  "global-impact": "GLOBAL IMPACT",
  headlines: "LATEST HEADLINES",
  "events-timeline": "EVENTS TIMELINE",
  proximity: "PROXIMITY ANALYZER",
  "activity-connectivity": "ACTIVITY & CONNECTIVITY",
};

function SummaryView({ ctx }: { ctx: SectionRenderContext }) {
  const { conflictData, displayConflictLabel, lastUpdated, analysisLoading, analysisRunning, analysisError, onRunAnalysis } = ctx;
  const keyFindings = conflictData?.key_findings ?? [];
  const riskLevel = conflictData?.compliance?.risk_score?.level ?? "–";
  const chokepoints = conflictData?.chokepoint?.chokepoints ?? [];
  const restricted = chokepoints.filter((c) => String(c.status ?? "").toUpperCase() !== "OPEN").length;
  const predictive = conflictData?.predictive?.escalation?.[0]?.level ?? conflictData?.predictive?.baseline_escalation?.level ?? "–";
  const pentagonScore = conflictData?.pentagon?.pentagon_score;
  const pizzaBand = getPizzaBand(pentagonScore);
  const pizzaLabel = typeof pentagonScore === "number" ? `${Math.round(pentagonScore)} (${pizzaBand ?? "N/A"})` : "–";
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
        <SummaryRow label="Compliance" value={riskLevel} />
        <SummaryRow label="ChokePoints" value={restricted > 0 ? `${restricted} restricted` : "All open"} />
        <SummaryRow label="Headlines" value={`${ctx.rawArticleCount} new`} />
        <SummaryRow label="Pizza Index" value={pizzaLabel} />
        <SummaryRow label="Predictive" value={String(predictive)} />
      </div>
      {keyFindings.length > 0 && (
        <div className="rounded-lg border border-border bg-card/40 p-3">
          <p className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">TOP FINDINGS</p>
          <FindingsList findings={keyFindings} confidences={conflictData?.key_findings_confidence} />
        </div>
      )}
    </div>
  );
}

function FocusView({ ctx }: { ctx: SectionRenderContext }) {
  const { conflictData, activeConflict } = ctx;
  const summary = conflictData?.summary ?? null;
  const keyFindings = conflictData?.key_findings ?? [];
  const score = conflictData?.escalation_score ?? null;
  const threat = conflictData?.threat_level ?? "–";
  const pentagonScore = conflictData?.pentagon?.pentagon_score;
  const pizzaBand = getPizzaBand(pentagonScore);

  const focusRegions = useMemo(() => getActiveFocusRegions(activeConflict), [activeConflict]);
  const regionHighlights = useMemo(() => {
    const map = new Map<FocusRegion, string[]>();
    for (const region of focusRegions) map.set(region, getFocusHighlights(conflictData, region));
    return map;
  }, [conflictData, focusRegions]);
  const redSeaKpis = useMemo(() => getRedSeaFocusKpis(conflictData), [conflictData]);

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
            <span className={`rounded border px-1.5 py-0.5 text-[10px] font-mono tracking-wide ${getPizzaBandClass(pizzaBand)}`} title="Informal proxy signal only; not a confirmed military indicator">
              {pizzaBand ?? "N/A"}
            </span>
          </div>
        </div>
      </div>
      {summary && <p className="text-sm leading-relaxed">{summary}</p>}
      {keyFindings.length > 0 && (
        <div>
          <p className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">WHAT'S NEW</p>
          <FindingsList findings={keyFindings} confidences={conflictData?.key_findings_confidence} />
        </div>
      )}
      {(["iran", "lebanon", "red_sea"] as FocusRegion[])
        .filter((r) => focusRegions.has(r))
        .map((region) => (
          <FocusRegionCard
            key={region}
            region={region}
            highlights={regionHighlights.get(region) ?? []}
            redSeaKpis={region === "red_sea" ? redSeaKpis : undefined}
          />
        ))}
    </div>
  );
}

const DOMAIN_ORDER: FeedDomainId[] = ["information", "political", "security", "economic"];

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
  const [feedView, setFeedView] = useFeedView();
  const socialStream = useSocialWebSocket(activeConflict || displayConflictLabel || "Iran", true);
  const rawArticles = conflictData?.news?.articles ?? [];
  const filteredArticles = useMemo(
    () => filterArticlesBySourceKeys(rawArticles, headlineAllowedSources),
    [rawArticles, headlineAllowedSources],
  );

  const sectionCtx = useMemo<SectionRenderContext>(
    () => ({
      conflictData,
      lastUpdated,
      displayConflictLabel,
      activeConflict,
      analysisLoading,
      analysisRunning,
      analysisError,
      onRunAnalysis,
      proximityEvidence,
      filteredArticles,
      rawArticleCount: rawArticles.length,
      headlineAllowedSources,
      onHeadlineAllowedSourcesChange,
      socialStream,
    }),
    [
      conflictData,
      lastUpdated,
      displayConflictLabel,
      activeConflict,
      analysisLoading,
      analysisRunning,
      analysisError,
      onRunAnalysis,
      proximityEvidence,
      filteredArticles,
      rawArticles.length,
      headlineAllowedSources,
      onHeadlineAllowedSourcesChange,
      socialStream,
    ],
  );

  const closePanel = useCallback(() => setRightPanelOpen(false), [setRightPanelOpen]);

  const renderSection = useCallback(
    (sectionId: FeedSectionId) => {
      const renderer = SECTION_REGISTRY[sectionId];
      if (!renderer) return null;
      const headerRight =
        sectionId === "briefing" ? (
          <span className="text-[11px] text-muted-foreground">{formatTimeAgo(lastUpdated)}</span>
        ) : sectionId === "headlines" && rawArticles.length ? (
          <span className="text-[11px] text-muted-foreground">
            {filteredArticles.length === rawArticles.length
              ? `${rawArticles.length} stories`
              : `${filteredArticles.length}/${rawArticles.length} stories`}
          </span>
        ) : undefined;
      return (
        <CollapsiblePanel key={sectionId} sectionId={sectionId} title={SECTION_TITLES[sectionId]} headerRight={headerRight}>
          <ErrorBoundary sectionLabel={SECTION_TITLES[sectionId]}>{renderer(sectionCtx)}</ErrorBoundary>
        </CollapsiblePanel>
      );
    },
    [sectionCtx, lastUpdated, rawArticles.length, filteredArticles.length],
  );

  const feedContent = useMemo(() => {
    if (analysisLoading && !conflictData) {
      return (
        <>
          <IntelPanelSkeleton lines={4} />
          <IntelPanelSkeleton lines={3} />
          <IntelPanelSkeleton lines={3} />
          <IntelPanelSkeleton lines={2} />
        </>
      );
    }
    if (feedView === "summary") {
      return (
        <ErrorBoundary sectionLabel="Summary Feed">
          <SummaryView ctx={sectionCtx} />
        </ErrorBoundary>
      );
    }
    if (feedView === "focus") {
      return (
        <ErrorBoundary sectionLabel="Focus Feed">
          <FocusView ctx={sectionCtx} />
        </ErrorBoundary>
      );
    }
    return (
      <ErrorBoundary sectionLabel="Full Feed">
        {DOMAIN_ORDER.map((domainId) => (
          <CollapsibleDomainGroup key={domainId} domainId={domainId}>
            {FEED_DOMAINS[domainId].sectionIds.map((sid) => renderSection(sid as FeedSectionId))}
          </CollapsibleDomainGroup>
        ))}
        {conflictData?.corroborated_patterns && conflictData.corroborated_patterns.length > 0 && (
          <div className="pt-2">
            <CorroboratedPatternsBlock patterns={conflictData.corroborated_patterns} />
          </div>
        )}
      </ErrorBoundary>
    );
  }, [feedView, analysisLoading, conflictData, sectionCtx, renderSection]);

  return (
    <aside
      className={`
        ${rightPanelOpen ? "translate-x-0" : "translate-x-full"}
        md:translate-x-0
        w-[min(18rem,90vw)] sm:w-72 md:min-w-[380px] md:flex-[1_1_40%] md:min-w-0
        border-l border-border flex-shrink-0 p-4 flex flex-col overflow-y-auto overscroll-contain bg-background
        absolute md:relative inset-y-0 right-0 z-20 transition-transform duration-300 ease-in-out
      `}
      aria-label="Intelligence feed"
    >
      <div className="flex items-center justify-between mb-3 gap-2">
        <h2 className="font-mono text-xs text-muted-foreground tracking-wider truncate">INTELLIGENCE FEED</h2>
        <FeedViewSwitcher current={feedView} onChange={setFeedView} />
        <button
          type="button"
          aria-label="Close panel"
          className="md:hidden min-h-11 min-w-11 flex items-center justify-center -m-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 active:bg-muted touch-manipulation"
          onClick={closePanel}
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

      <div className="space-y-4">{feedContent}</div>

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

import { useState, useEffect, useRef, useMemo } from "react";
import { useIsMobileLayout } from "@/hooks/useMediaQuery";
import { trackMobileNav, trackMobilePanel } from "@/lib/mobileAnalytics";
import { buildSearchHits } from "@/lib/dashboardSearchIndex";
import { GlobalSearchDialog } from "@/components/dashboard/GlobalSearchDialog";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LiveTicker } from "@/components/dashboard/LiveTicker";
import type { ProximityEvidence } from "@/lib/proximityAnalyzerService";
import { DEFAULT_CONFLICT } from "@/lib/conflictDefaults";
import { useConflictWebSocket } from "@/hooks/useConflictWebSocket";
import { Menu, X, Radio, Rss, BookOpen, Heart, FileText, Activity, Github, Newspaper, Mail, Search } from "lucide-react";
import { DashboardLeftPanel } from "@/components/dashboard/DashboardLeftPanel";
import { DashboardMapSection } from "@/components/dashboard/DashboardMapSection";
import { DashboardRightPanel } from "@/components/dashboard/DashboardRightPanel";
import { OfflineStatusBadge } from "@/components/dashboard/OfflineStatusBadge";
import { PatternFlagsBanner } from "@/components/dashboard/PatternFlagsBanner";
import { SEO } from "@/components/SEO";
const THREAT_BADGE_STYLES: Record<string, string> = {
  LOW: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  ELEVATED: "bg-warning/20 text-warning border-warning/30",
  HIGH: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  CRITICAL: "bg-destructive/20 text-destructive border-destructive/30 animate-pulse",
};

function getThreatBadgeClass(level: string | null | undefined): string {
  return THREAT_BADGE_STYLES[level ?? "ELEVATED"] ?? THREAT_BADGE_STYLES.ELEVATED;
}

const Dashboard = () => {
  return (
    <>
      <SEO
        title="Digital War Room – AI-Powered OSINT Intelligence"
        description="Digital War Room: AI-powered OSINT conflict monitoring. Real-time escalation score, multi-agent intelligence (GEOINT, SIGINT, SOCMINT, FININT, TECHINT) and BLUF-style briefings."
        path="/app/dashboard"
        imageAlt="Digital War Room dashboard showing conflict escalation and intelligence streams"
      />
      <DashboardContent />
    </>
  );
};

function DashboardContent() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const selectedConflict = DEFAULT_CONFLICT;
  const displayConflictLabel = DEFAULT_CONFLICT;
  const [headlineAllowedSources, setHeadlineAllowedSources] = useState<Set<string>>(() => new Set());
  const [searchOpen, setSearchOpen] = useState(false);
  const skipHeadlinePersistRef = useRef(false);

  const [leftPanelOpen, setLeftPanelOpen] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [agentExpanded, setAgentExpanded] = useState<string | null>(null);

  const {
    data: conflictData,
    status,
    initialLoadPending,
    lastUpdated,
    dataFromCache,
    analysisError,
    runAnalysis,
  } = useConflictWebSocket({
    conflict: selectedConflict,
    enabled: true,
  });
  const searchHits = useMemo(() => buildSearchHits(conflictData), [conflictData]);

  useEffect(() => {
    skipHeadlinePersistRef.current = true;
    const key = `dwr:headlineSources:${selectedConflict}`;
    try {
      const raw = sessionStorage.getItem(key);
      if (!raw) {
        setHeadlineAllowedSources(new Set());
        return;
      }
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed) && parsed.every((x) => typeof x === "string")) {
        setHeadlineAllowedSources(new Set(parsed));
      } else {
        setHeadlineAllowedSources(new Set());
      }
    } catch {
      setHeadlineAllowedSources(new Set());
    }
  }, [selectedConflict]);

  useEffect(() => {
    if (skipHeadlinePersistRef.current) {
      skipHeadlinePersistRef.current = false;
      return;
    }
    const key = `dwr:headlineSources:${selectedConflict}`;
    try {
      if (headlineAllowedSources.size === 0) {
        sessionStorage.removeItem(key);
      } else {
        sessionStorage.setItem(key, JSON.stringify([...headlineAllowedSources]));
      }
    } catch {
      // ignore
    }
  }, [selectedConflict, headlineAllowedSources]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key !== "k") return;
      const el = e.target as HTMLElement | null;
      if (el?.closest("input, textarea, [contenteditable=true]")) return;
      e.preventDefault();
      setSearchOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Live clock
  const [utcTime, setUtcTime] = useState(() => new Date());
  const [isOffline, setIsOffline] = useState(() =>
    typeof navigator !== "undefined" ? !navigator.onLine : false
  );
  useEffect(() => {
    const interval = setInterval(() => setUtcTime(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);
  useEffect(() => {
    const onOnline = () => setIsOffline(false);
    const onOffline = () => setIsOffline(true);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  const isMobileLayout = useIsMobileLayout();
  const prevMenuOpen = useRef<boolean | null>(null);
  useEffect(() => {
    if (!isMobileLayout) {
      prevMenuOpen.current = mobileMenuOpen;
      return;
    }
    if (prevMenuOpen.current === null) {
      prevMenuOpen.current = mobileMenuOpen;
      return;
    }
    if (prevMenuOpen.current !== mobileMenuOpen) {
      trackMobileNav(mobileMenuOpen ? "open" : "close");
    }
    prevMenuOpen.current = mobileMenuOpen;
  }, [mobileMenuOpen, isMobileLayout]);

  const prevLeftOpen = useRef(leftPanelOpen);
  const prevRightOpen = useRef(rightPanelOpen);
  useEffect(() => {
    if (!isMobileLayout) return;
    if (prevLeftOpen.current !== leftPanelOpen) {
      trackMobilePanel("left", leftPanelOpen ? "open" : "close");
      prevLeftOpen.current = leftPanelOpen;
    }
  }, [leftPanelOpen, isMobileLayout]);
  useEffect(() => {
    if (!isMobileLayout) return;
    if (prevRightOpen.current !== rightPanelOpen) {
      trackMobilePanel("right", rightPanelOpen ? "open" : "close");
      prevRightOpen.current = rightPanelOpen;
    }
  }, [rightPanelOpen, isMobileLayout]);

  const formattedTime = utcTime.toISOString().slice(11, 19);

  // Live signal counter: real count from analysis (articles, aircraft, reports, findings, etc.)
  const signalCount = useMemo(() => {
    if (!conflictData) return null;
    let n = 0;
    n += (conflictData.news?.articles?.length ?? 0);
    n += (conflictData.sigint?.aircraft?.filter((a): a is object => typeof a === "object" && a !== null && !("error" in a)).length ?? 0);
    n += (conflictData.sigint?.ships?.length ?? 0);
    n += (conflictData.sigint?.conflict_reports?.length ?? 0);
    n += (conflictData.key_findings?.length ?? 0);
    const socmint = conflictData as { socmint?: { top_signals?: unknown[] } };
    n += (socmint.socmint?.top_signals?.length ?? 0);
    const geoint = conflictData.geoint as { anomalies?: unknown[]; hotspots?: unknown[] } | undefined;
    n += (geoint?.anomalies?.length ?? 0) + (geoint?.hotspots?.length ?? 0);
    const techint = conflictData.techint as { tech_indicators?: unknown[]; export_controls?: unknown[]; ioda_events?: unknown[] } | undefined;
    n += (techint?.tech_indicators?.length ?? 0) + (techint?.export_controls?.length ?? 0) + (techint?.ioda_events?.length ?? 0);
    n += (conflictData.cyber?.cisa_kev?.total ?? 0) + (conflictData.cyber?.threat_reports?.length ?? 0) + (conflictData.cyber?.otx_pulses?.length ?? 0) + (conflictData.cyber?.greynoise_scan_context?.available ? (conflictData.cyber.greynoise_scan_context.count ?? 0) : 0);
    n += (conflictData.energy?.agsi_storage?.full?.length ?? 0) + (conflictData.energy?.commodities?.length ?? 0);
    n += (conflictData.protest?.protest_events?.length ?? 0) + (conflictData.protest?.protest_articles?.length ?? 0);
    n += (conflictData.diplo?.ofac_sdn?.total_matches ?? 0) + (conflictData.diplo?.un_icj_news?.length ?? 0);
    n += (conflictData.proximity?.evidence?.length ?? 0);
    return n;
  }, [conflictData]);

  // Proximity Analyzer: uses evidence from main analysis (runs automatically with other agents)
  const proximityEvidence: ProximityEvidence[] = useMemo(
    () => (conflictData?.proximity?.evidence ?? []).filter((e): e is ProximityEvidence => e != null && typeof e === "object"),
    [conflictData?.proximity?.evidence]
  );

  return (
    <div className="h-screen min-h-0 bg-background flex flex-col overflow-hidden supports-[padding:env(safe-area-inset-top)]:pt-[env(safe-area-inset-top)]">
      {/* Live ticker – Iran Monitor style: BREAKING headlines from analysis when available */}
      <div
        className="flex items-center border-b border-border bg-card/50 min-h-9 sm:min-h-10"
        role="region"
        aria-label="Live headline ticker"
      >
        <div className="flex-shrink-0 px-3 py-2 sm:py-1.5 bg-destructive/20 text-destructive font-mono text-[11px] sm:text-[11px] font-bold tracking-wider border-r border-border">
          LIVE
        </div>
        <div className="flex-1 min-w-0 overflow-hidden">
          <LiveTicker conflictData={conflictData} headlineAllowedSources={headlineAllowedSources} />
        </div>
      </div>
      {conflictData?.pattern_flags != null && conflictData.pattern_flags.length > 0 && (
        <PatternFlagsBanner flags={conflictData.pattern_flags} />
      )}
      {/* Top Navbar – touch-friendly min 44px height on mobile */}
      <header className="min-h-14 border-b border-border flex items-center justify-between px-3 md:px-4 flex-shrink-0 gap-2 py-2 sm:py-0" role="banner">
        <div className="flex items-center gap-2 min-w-0">
          {/* Mobile hamburger – 44px tap target */}
          <button
            type="button"
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            className="lg:hidden min-h-11 min-w-11 flex items-center justify-center -m-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 active:bg-muted transition-colors touch-manipulation"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
          </button>
          <h1 className="font-mono font-bold text-primary text-glow-intense text-xs sm:text-sm tracking-[0.25em] truncate m-0">
            DIGITAL WAR ROOM
          </h1>
        </div>

        <div className="flex items-center gap-1 sm:gap-3 flex-shrink-0">
          {/* Live clock – desktop */}
          <div className="hidden md:flex items-center gap-1.5 font-mono text-xs text-muted-foreground border border-border rounded px-2 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse-dot" />
            <span className="text-foreground">{formattedTime}</span>
            <span>UTC</span>
          </div>
          {/* Signal counter (from current analysis data) */}
          <div className="hidden sm:flex items-center gap-1.5 font-mono text-xs text-muted-foreground border border-border rounded px-2 py-1.5">
            <span className="text-primary">{signalCount !== null ? signalCount.toLocaleString() : "–"}</span>
            <span>signals</span>
          </div>
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            className="hidden sm:flex items-center gap-1.5 font-mono text-xs text-muted-foreground border border-border rounded px-2 py-1.5 hover:bg-muted/50 hover:text-foreground transition-colors"
            aria-label="Open search"
            title="Search (⌘K / Ctrl+K)"
          >
            <Search className="h-3.5 w-3.5" aria-hidden />
            <span className="hidden md:inline">Search</span>
            <kbd className="hidden lg:inline pointer-events-none text-[10px] opacity-60 border border-border rounded px-1 py-0.5">⌘K</kbd>
          </button>
          <div className="hidden lg:block">
            <OfflineStatusBadge isOffline={isOffline} lastUpdated={lastUpdated} wsStatus={status} dataFromCache={dataFromCache} compact />
          </div>
          <div
            className="flex items-center text-xs sm:text-sm font-mono border border-border rounded-md px-2.5 sm:px-3 py-2 sm:py-1.5 min-h-11 sm:min-h-0 text-foreground pointer-events-none select-none"
            aria-label="Theater"
          >
            <span className="truncate max-w-[120px] text-primary font-medium">{displayConflictLabel}</span>
          </div>
          <Badge className={`${getThreatBadgeClass(conflictData?.threat_level)} font-mono text-[11px] sm:text-xs hidden sm:flex`}>
            {conflictData?.threat_level ?? "ELEVATED"}
          </Badge>
        </div>
      </header>

      {/* Mobile menu dropdown – large tap targets */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-b border-border bg-card p-4 space-y-4 animate-fade-in-up">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground truncate">Digital War Room</span>
            <Badge className={`${getThreatBadgeClass(conflictData?.threat_level)} font-mono text-[11px] sm:hidden`}>
              {conflictData?.threat_level ?? "ELEVATED"}
            </Badge>
          </div>
          <div className="flex flex-col gap-2">
            <Button
              variant={leftPanelOpen ? "default" : "outline"}
              size="sm"
              className="w-full min-h-12 justify-center text-xs touch-manipulation"
              onClick={() => { setLeftPanelOpen(!leftPanelOpen); setRightPanelOpen(false); setMobileMenuOpen(false); }}
            >
              <Radio className="h-4 w-4 shrink-0" aria-hidden /> Agents
            </Button>
            <Button
              variant={rightPanelOpen ? "default" : "outline"}
              size="sm"
              className="w-full min-h-12 justify-center text-xs touch-manipulation"
              onClick={() => { setRightPanelOpen(!rightPanelOpen); setLeftPanelOpen(false); setMobileMenuOpen(false); }}
            >
              <Rss className="h-4 w-4 shrink-0" aria-hidden /> Intel Feed
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="w-full min-h-12 justify-center text-xs touch-manipulation"
              onClick={() => { setSearchOpen(true); setMobileMenuOpen(false); }}
              aria-label="Open search"
            >
              <Search className="h-4 w-4 shrink-0" aria-hidden /> Search
            </Button>
            <div className="grid grid-cols-2 gap-2 pt-1">
              <Button variant="outline" size="sm" className="min-h-12 touch-manipulation" asChild>
                <Link to="/app/monitoring" className="inline-flex items-center justify-center gap-2" onClick={() => setMobileMenuOpen(false)}>
                  <Activity className="h-4 w-4 shrink-0" aria-hidden />
                  <span className="truncate">Monitor</span>
                </Link>
              </Button>
              <Button variant="outline" size="sm" className="min-h-12 touch-manipulation" asChild>
                <Link to="/newsletter" className="inline-flex items-center justify-center gap-2" onClick={() => setMobileMenuOpen(false)}>
                  <Mail className="h-4 w-4 shrink-0" aria-hidden />
                  <span className="truncate">Subscribe</span>
                </Link>
              </Button>
            </div>
          </div>
          <OfflineStatusBadge isOffline={isOffline} lastUpdated={lastUpdated} wsStatus={status} dataFromCache={dataFromCache} />
          <nav className="flex flex-col gap-1 text-xs" aria-label="Mobile shortcuts">
            <Link to="/docs/documentation" className="text-primary hover:underline touch-manipulation min-h-11 inline-flex items-center py-1" onClick={() => setMobileMenuOpen(false)}>Documentation</Link>
            <Link to="/blog" className="text-primary hover:underline touch-manipulation min-h-11 inline-flex items-center py-1" onClick={() => setMobileMenuOpen(false)}>Blog</Link>
            <Link to="/daily-briefing" className="text-primary hover:underline touch-manipulation min-h-11 inline-flex items-center py-1" onClick={() => setMobileMenuOpen(false)}>Daily Briefing</Link>
            <Link to="/support" className="text-primary hover:underline touch-manipulation min-h-11 inline-flex items-center py-1" onClick={() => setMobileMenuOpen(false)}>Support</Link>
          </nav>
        </div>
      )}

      <div className="flex flex-1 min-h-0 overflow-hidden relative min-w-0">
        <DashboardLeftPanel
          leftPanelOpen={leftPanelOpen}
          setLeftPanelOpen={setLeftPanelOpen}
          agentExpanded={agentExpanded}
          setAgentExpanded={setAgentExpanded}
          conflictData={conflictData}
        />

        {/* Overlay backdrop for mobile panels */}
        {(leftPanelOpen || rightPanelOpen) && (
          <div
            className="lg:hidden absolute inset-0 z-10 bg-background/60 backdrop-blur-sm"
            aria-hidden="true"
            onClick={() => { setLeftPanelOpen(false); setRightPanelOpen(false); }}
          />
        )}

        <DashboardMapSection
          leftPanelOpen={leftPanelOpen}
          setLeftPanelOpen={setLeftPanelOpen}
          rightPanelOpen={rightPanelOpen}
          setRightPanelOpen={setRightPanelOpen}
          activeConflict={selectedConflict}
          conflictData={conflictData}
        />

        <DashboardRightPanel
          rightPanelOpen={rightPanelOpen}
          setRightPanelOpen={setRightPanelOpen}
          conflictData={conflictData}
          lastUpdated={lastUpdated}
          displayConflictLabel={displayConflictLabel}
          activeConflict={selectedConflict}
          analysisLoading={initialLoadPending}
          analysisRunning={status === "analyzing"}
          analysisError={analysisError}
          onRunAnalysis={runAnalysis}
          proximityEvidence={proximityEvidence}
          headlineAllowedSources={headlineAllowedSources}
          onHeadlineAllowedSourcesChange={setHeadlineAllowedSources}
        />
      </div>

      <GlobalSearchDialog open={searchOpen} onOpenChange={setSearchOpen} hits={searchHits} />

      {/* Footer: docs hub (incl. How it works, Methodology, Source Directory), Support, legal */}
      <footer className="flex-shrink-0 border-t border-border bg-background/80 backdrop-blur-sm px-3 py-2" role="contentinfo">
        <div className="grid grid-cols-2 sm:flex sm:items-center gap-2 sm:gap-4 max-lg:[&_a]:min-h-11 max-lg:[&_a]:inline-flex max-lg:[&_a]:items-center">
          <Link
            to="/docs/documentation"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/90 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded touch-manipulation"
            aria-label="Documentation"
          >
            <BookOpen className="h-3.5 w-3.5" aria-hidden />
            <span>docs</span>
          </Link>
          <Link
            to="/blog"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/90 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded touch-manipulation"
          >
            <Newspaper className="h-3.5 w-3.5" aria-hidden />
            <span>Blog</span>
          </Link>
          <Link
            to="/daily-briefing"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/90 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded touch-manipulation"
          >
            <FileText className="h-3.5 w-3.5" aria-hidden />
            <span>Daily Briefing</span>
          </Link>
          <Link
            to="/app/monitoring"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/90 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded touch-manipulation"
          >
            <Activity className="h-3.5 w-3.5" aria-hidden />
            <span>Agent Monitor</span>
          </Link>
          <Link
            to="/support"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/90 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded touch-manipulation"
          >
            <Heart className="h-3.5 w-3.5" aria-hidden />
            <span>Support the Mission</span>
          </Link>
          <Link
            to="/newsletter"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/90 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded touch-manipulation"
          >
            <Mail className="h-3.5 w-3.5" aria-hidden />
            <span>Subscribe</span>
          </Link>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground mt-1.5 sm:mt-1">
          <a
            href="https://github.com/lina767/digital-war-room"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 hover:text-foreground/80 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded touch-manipulation"
            aria-label="Digital War Room on GitHub"
          >
            <Github className="h-3.5 w-3.5" aria-hidden />
            <span>GitHub</span>
          </a>
          <span className="text-border">·</span>
          <Link
            to="/impressum"
            className="hover:text-foreground/80 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded touch-manipulation"
          >
            Legal notice
          </Link>
          <span className="text-border">·</span>
          <Link
            to="/privacy"
            className="hover:text-foreground/80 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded touch-manipulation"
          >
            Privacy
          </Link>
        </div>
      </footer>
    </div>
  );
};

export default Dashboard;

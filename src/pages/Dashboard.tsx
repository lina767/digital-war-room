import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LiveTicker } from "@/components/dashboard/LiveTicker";
import { runProximityAnalysis, fetchTunnelSites } from "@/lib/proximityAnalyzerService";
import type { ProximityEvidence } from "@/lib/proximityAnalyzerService";
import { CONFLICT_OPTIONS } from "@/components/dashboard/conflictData";
import { useConflictWebSocket } from "@/hooks/useConflictWebSocket";
import { ChevronDown, Menu, X, Radio, Rss, BookOpen, Heart, Database } from "lucide-react";
import { DashboardLeftPanel } from "@/components/dashboard/DashboardLeftPanel";
import { DashboardMapSection } from "@/components/dashboard/DashboardMapSection";
import { DashboardRightPanel } from "@/components/dashboard/DashboardRightPanel";

const Dashboard = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [conflictDropdownOpen, setConflictDropdownOpen] = useState(false);
  const conflictDropdownRef = useRef<HTMLDivElement>(null);

  const [selectedConflict, setSelectedConflict] = useState<string>(CONFLICT_OPTIONS[0]?.apiValue ?? "Iran");

  const [leftPanelOpen, setLeftPanelOpen] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [agentExpanded, setAgentExpanded] = useState<string | null>(null);

  const { data: conflictData, status: analysisStatus, runAnalysis, lastUpdated, analysisError } = useConflictWebSocket({
    conflict: selectedConflict,
    enabled: true,
  });
  const isAnalyzing = analysisStatus === "analyzing";
  const currentOption = CONFLICT_OPTIONS.find((o) => o.apiValue === selectedConflict);
  const displayConflictLabel = currentOption?.label ?? selectedConflict;

  useEffect(() => {
    const onOutside = (e: MouseEvent) => {
      if (conflictDropdownRef.current && !conflictDropdownRef.current.contains(e.target as Node)) setConflictDropdownOpen(false);
    };
    document.addEventListener("click", onOutside);
    return () => document.removeEventListener("click", onOutside);
  }, []);

  // Live clock
  const [utcTime, setUtcTime] = useState(() => new Date());
  useEffect(() => {
    const interval = setInterval(() => setUtcTime(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);
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

  // Proximity Analyzer: strike–civilian correlation
  const [proximityEvidence, setProximityEvidence] = useState<ProximityEvidence[]>([]);
  const [proximityLoading, setProximityLoading] = useState(false);
  const [proximityError, setProximityError] = useState<string | null>(null);
  const conflictToRegion = (c: string): string => {
    const lower = c.toLowerCase();
    if (lower.includes("iran") || lower.includes("israel") || lower.includes("gaza") || lower.includes("yemen") || lower.includes("syria") || lower.includes("iraq") || lower.includes("lebanon")) return "middle_east";
    if (lower.includes("ukraine") || lower.includes("russia")) return "eastern_europe";
    if (lower.includes("taiwan") || lower.includes("korea") || lower.includes("myanmar")) return "east_asia";
    if (lower.includes("sudan") || lower.includes("ethiopia") || lower.includes("sahel") || lower.includes("drc")) return "africa";
    return "middle_east";
  };
  const runProximity = useCallback(async () => {
    setProximityLoading(true);
    setProximityError(null);
    try {
      const region = conflictToRegion(selectedConflict);
      // For Iran: load tunnel/sites GeoJSON to flag PROBABLE_HUMAN_SHIELD (IRGC tunnels vs. schools/hospitals)
      const useTunnelSites = selectedConflict.toLowerCase().includes("iran");
      const tunnelSites = useTunnelSites ? await fetchTunnelSites() : null;
      const evidence = await runProximityAnalysis(region, 3, tunnelSites ?? undefined);
      setProximityEvidence(evidence);
    } catch (e) {
      setProximityError(e instanceof Error ? e.message : String(e));
      setProximityEvidence([]);
    } finally {
      setProximityLoading(false);
    }
  }, [selectedConflict]);

  return (
    <div className="h-screen min-h-0 bg-background flex flex-col overflow-hidden supports-[padding:env(safe-area-inset-top)]:pt-[env(safe-area-inset-top)]">
      {/* Live ticker – Iran Monitor style: BREAKING headlines from analysis when available */}
      <div className="flex items-center border-b border-border bg-card/50 min-h-9 sm:min-h-10">
        <div className="flex-shrink-0 px-3 py-2 sm:py-1.5 bg-destructive/20 text-destructive font-mono text-[10px] sm:text-[10px] font-bold tracking-wider border-r border-border">
          LIVE
        </div>
        <div className="flex-1 min-w-0 overflow-hidden">
          <LiveTicker conflictData={conflictData} />
        </div>
      </div>
      {/* Top Navbar – touch-friendly min 44px height on mobile */}
      <header className="min-h-14 border-b border-border flex items-center justify-between px-3 md:px-4 flex-shrink-0 gap-2 py-2 sm:py-0">
        <div className="flex items-center gap-2 min-w-0">
          {/* Mobile hamburger – 44px tap target */}
          <button
            type="button"
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            className="lg:hidden min-h-11 min-w-11 flex items-center justify-center -m-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 active:bg-muted transition-colors touch-manipulation"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <div className="font-mono font-bold text-primary text-glow text-xs sm:text-sm tracking-wider truncate">
            DIGITAL WAR ROOM
          </div>
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
            <span className="text-primary">{signalCount !== null ? signalCount.toLocaleString() : "—"}</span>
            <span>signals</span>
          </div>
          <div className="relative" ref={conflictDropdownRef}>
            <button
              type="button"
              className="flex items-center gap-1 text-xs sm:text-sm font-mono border border-border rounded-md px-2.5 sm:px-3 py-2 sm:py-1.5 min-h-11 sm:min-h-0 hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors touch-manipulation"
              onClick={() => setConflictDropdownOpen((o) => !o)}
            >
              <span className="hidden sm:inline truncate max-w-[120px]">{displayConflictLabel}</span>
              <span className="sm:hidden truncate max-w-[80px]">{currentOption?.id ?? selectedConflict}</span>
              <ChevronDown className={`h-3 w-3 flex-shrink-0 transition-transform ${conflictDropdownOpen ? "rotate-180" : ""}`} />
            </button>
            {conflictDropdownOpen && (
              <div className="absolute top-full right-0 mt-1 w-52 sm:w-48 max-h-[70vh] overflow-y-auto rounded-md border border-border bg-background shadow-lg z-50 py-1">
                {CONFLICT_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className="w-full flex items-center gap-2 px-3 py-3 sm:py-2 text-left text-xs font-mono hover:bg-muted active:bg-muted min-h-11 sm:min-h-0 touch-manipulation"
                    onClick={() => {
                      setSelectedConflict(opt.apiValue);
                      setConflictDropdownOpen(false);
                    }}
                  >
                    <span className={selectedConflict === opt.apiValue ? "text-primary font-medium" : ""}>{opt.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <Badge className="bg-warning/20 text-warning border-warning/30 font-mono text-[10px] sm:text-xs hidden sm:flex">
            {conflictData?.threat_level ?? "ELEVATED"}
          </Badge>
          <div className="flex flex-col items-end gap-1">
            {analysisError && (
              <p className="text-[10px] text-destructive max-w-[200px] sm:max-w-[320px] text-right truncate" title={analysisError}>
                {analysisError}
              </p>
            )}
            <Button
              size="sm"
              className="text-xs px-3 sm:px-3 min-h-11 sm:min-h-9 touch-manipulation"
              disabled={isAnalyzing}
              onClick={() => runAnalysis()}
              title="Load latest analysis (cache / periodic auto-run)"
            >
              {isAnalyzing ? (
                <span className="animate-pulse">Loading…</span>
              ) : (
                "Analyze"
              )}
            </Button>
          </div>
        </div>
      </header>

      {/* Mobile menu dropdown – large tap targets */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-b border-border bg-card p-4 space-y-4 animate-fade-in-up">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground truncate">Digital War Room</span>
            <Badge className="bg-warning/20 text-warning border-warning/30 font-mono text-[10px] sm:hidden">
              {conflictData?.threat_level ?? "ELEVATED"}
            </Badge>
          </div>
          <div className="flex gap-3">
            <Button
              variant={leftPanelOpen ? "default" : "outline"}
              size="sm"
              className="flex-1 min-h-11 text-xs touch-manipulation"
              onClick={() => { setLeftPanelOpen(!leftPanelOpen); setRightPanelOpen(false); setMobileMenuOpen(false); }}
            >
              <Radio className="h-4 w-4 mr-2" aria-hidden /> Agents
            </Button>
            <Button
              variant={rightPanelOpen ? "default" : "outline"}
              size="sm"
              className="flex-1 min-h-11 text-xs touch-manipulation"
              onClick={() => { setRightPanelOpen(!rightPanelOpen); setLeftPanelOpen(false); setMobileMenuOpen(false); }}
            >
              <Rss className="h-4 w-4 mr-2" aria-hidden /> Intel Feed
            </Button>
          </div>
        </div>
      )}

      <div className="flex flex-1 min-h-0 overflow-hidden relative min-w-0">
        <DashboardLeftPanel
          leftPanelOpen={leftPanelOpen}
          setLeftPanelOpen={setLeftPanelOpen}
          agentExpanded={agentExpanded}
          setAgentExpanded={setAgentExpanded}
        />

        {/* Overlay backdrop for mobile panels */}
        {(leftPanelOpen || rightPanelOpen) && (
          <div
            className="lg:hidden absolute inset-0 z-10 bg-background/60 backdrop-blur-sm"
            onClick={() => { setLeftPanelOpen(false); setRightPanelOpen(false); }}
          />
        )}

        <DashboardMapSection
          leftPanelOpen={leftPanelOpen}
          setLeftPanelOpen={setLeftPanelOpen}
          rightPanelOpen={rightPanelOpen}
          setRightPanelOpen={setRightPanelOpen}
          activeConflict={selectedConflict}
        />

        <DashboardRightPanel
          rightPanelOpen={rightPanelOpen}
          setRightPanelOpen={setRightPanelOpen}
          conflictData={conflictData}
          lastUpdated={lastUpdated}
          displayConflictLabel={displayConflictLabel}
          proximityEvidence={proximityEvidence}
          proximityLoading={proximityLoading}
          proximityError={proximityError}
          runProximity={runProximity}
        />
      </div>

      {/* Footer: How it works, Support (prominent), Impressum & Privacy (subtle) */}
      <footer className="flex-shrink-0 border-t border-border bg-background/80 backdrop-blur-sm px-3 py-2 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-4">
          <Link
            to="/how-it-works"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/90 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded touch-manipulation"
          >
            <BookOpen className="h-3.5 w-3.5" aria-hidden />
            <span>How it works</span>
          </Link>
          <Link
            to="/sources"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/90 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded touch-manipulation"
          >
            <Database className="h-3.5 w-3.5" aria-hidden />
            <span>Source Directory</span>
          </Link>
          <Link
            to="/support"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/90 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded touch-manipulation"
          >
            <Heart className="h-3.5 w-3.5" aria-hidden />
            <span>Support the Mission</span>
          </Link>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <Link
            to="/impressum"
            className="hover:text-foreground/80 transition-colors touch-manipulation"
          >
            Impressum
          </Link>
          <span className="text-border">·</span>
          <Link
            to="/privacy"
            className="hover:text-foreground/80 transition-colors touch-manipulation"
          >
            Privacy
          </Link>
        </div>
      </footer>
    </div>
  );
};

export default Dashboard;

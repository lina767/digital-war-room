import { useState, useEffect, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LiveTicker } from "@/components/dashboard/LiveTicker";
import { runProximityAnalysis, fetchTunnelSites } from "@/lib/proximityAnalyzerService";
import type { ProximityEvidence } from "@/lib/proximityAnalyzerService";
import { CONFLICT_OPTIONS } from "@/components/dashboard/conflictData";
import { useConflictWebSocket } from "@/hooks/useConflictWebSocket";
import { ChevronDown, Menu, X, Radio, Rss } from "lucide-react";
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

  // Live signal counter
  const [signalCount, setSignalCount] = useState(847);
  useEffect(() => {
    const interval = setInterval(() => {
      setSignalCount(prev => prev + Math.floor(Math.random() * 3));
    }, 4000 + Math.random() * 3000);
    return () => clearInterval(interval);
  }, []);

  // Proximity Analyzer: strike–civilian correlation
  const [proximityEvidence, setProximityEvidence] = useState<ProximityEvidence[]>([]);
  const [proximityLoading, setProximityLoading] = useState(false);
  const [proximityError, setProximityError] = useState<string | null>(null);
  const conflictToRegion = (c: string): string => {
    const lower = c.toLowerCase();
    if (lower.includes("iran") || lower.includes("israel") || lower.includes("gaza") || lower.includes("yemen") || lower.includes("syria") || lower.includes("iraq")) return "middle_east";
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
    <div className="h-screen min-h-0 bg-background flex flex-col overflow-hidden">
      {/* Live ticker – Iran Monitor style: BREAKING headlines from analysis when available */}
      <div className="flex items-center border-b border-border bg-card/50">
        <div className="flex-shrink-0 px-3 py-1.5 bg-destructive/20 text-destructive font-mono text-[10px] font-bold tracking-wider border-r border-border">
          LIVE
        </div>
        <div className="flex-1 min-w-0">
          <LiveTicker conflictData={conflictData} />
        </div>
      </div>
      {/* Top Navbar */}
      <header className="h-14 border-b border-border flex items-center justify-between px-3 md:px-4 flex-shrink-0 gap-2">
        <div className="flex items-center gap-2">
          {/* Mobile hamburger */}
          <button
            className="lg:hidden text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <div className="font-mono font-bold text-primary text-glow text-xs sm:text-sm tracking-wider">
            DIGITAL WAR ROOM
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          {/* Live clock */}
          <div className="hidden md:flex items-center gap-1.5 font-mono text-xs text-muted-foreground border border-border rounded px-2 py-1">
            <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse-dot" />
            <span className="text-foreground">{formattedTime}</span>
            <span>UTC</span>
          </div>
          {/* Signal counter */}
          <div className="hidden sm:flex items-center gap-1.5 font-mono text-xs text-muted-foreground border border-border rounded px-2 py-1">
            <span className="text-primary">{signalCount.toLocaleString()}</span>
            <span>signals</span>
          </div>
          <div className="relative" ref={conflictDropdownRef}>
            <button
              type="button"
              className="flex items-center gap-1 text-xs sm:text-sm font-mono border border-border rounded px-2 sm:px-3 py-1 hover:bg-secondary transition-colors"
              onClick={() => setConflictDropdownOpen((o) => !o)}
            >
              <span className="hidden sm:inline">{displayConflictLabel}</span>
              <span className="sm:hidden">{currentOption?.id ?? selectedConflict}</span>
              <ChevronDown className={`h-3 w-3 transition-transform ${conflictDropdownOpen ? "rotate-180" : ""}`} />
            </button>
            {conflictDropdownOpen && (
              <div className="absolute top-full right-0 mt-1 w-48 max-h-64 overflow-y-auto rounded border border-border bg-background shadow-lg z-50 py-1">
                {CONFLICT_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs font-mono hover:bg-muted"
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
              <p className="text-[10px] text-destructive max-w-[280px] sm:max-w-[320px] text-right" title={analysisError}>
                {analysisError}
              </p>
            )}
            <Button
              size="sm"
              className="text-xs px-2 sm:px-3"
              disabled={isAnalyzing}
              onClick={() => runAnalysis()}
              title="Letzte Analyse laden (Cache / stündliche Automatik)"
            >
              {isAnalyzing ? (
                <span className="animate-pulse">Laden…</span>
              ) : (
                <>
                  <span className="hidden sm:inline">Analyze</span>
                  <span className="sm:hidden">Analyze</span>
                </>
              )}
            </Button>
          </div>
          {/* Auth/Profile UI entfernt – Dashboard ist vollständig öffentlich */}
        </div>
      </header>

      {/* Mobile menu dropdown */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-b border-border bg-card p-4 space-y-4 animate-fade-in-up">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground truncate">Digital War Room</span>
            <Badge className="bg-warning/20 text-warning border-warning/30 font-mono text-[10px] sm:hidden">
              {conflictData?.threat_level ?? "ELEVATED"}
            </Badge>
          </div>
          <div className="flex gap-2">
            <Button
              variant={leftPanelOpen ? "default" : "outline"}
              size="sm"
              className="flex-1 text-xs"
              onClick={() => { setLeftPanelOpen(!leftPanelOpen); setRightPanelOpen(false); setMobileMenuOpen(false); }}
            >
              <Radio className="h-3 w-3 mr-1" /> Agents
            </Button>
            <Button
              variant={rightPanelOpen ? "default" : "outline"}
              size="sm"
              className="flex-1 text-xs"
              onClick={() => { setRightPanelOpen(!rightPanelOpen); setLeftPanelOpen(false); setMobileMenuOpen(false); }}
            >
              <Rss className="h-3 w-3 mr-1" /> Intel Feed
            </Button>
          </div>
        </div>
      )}

      <div className="flex flex-1 min-h-0 overflow-hidden relative">
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
    </div>
  );
};

export default Dashboard;

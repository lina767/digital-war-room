import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ConflictMap } from "@/components/dashboard/ConflictMap";
import { LiveTicker } from "@/components/dashboard/LiveTicker";
import { DailyBriefing } from "@/components/dashboard/DailyBriefing";
import { LatestHeadlines } from "@/components/dashboard/LatestHeadlines";
import { EventsTimeline } from "@/components/dashboard/EventsTimeline";
import { NewsSentiment } from "@/components/dashboard/NewsSentiment";
import { InternetConnectivity } from "@/components/dashboard/InternetConnectivity";
import { FlightRadar } from "@/components/dashboard/FlightRadar";
import { PredictionMarkets } from "@/components/dashboard/PredictionMarkets";
import { AGENTS_WITH_SOURCES } from "@/components/dashboard/agentsConfig";
import { CONFLICT_OPTIONS } from "@/components/dashboard/conflictData";
import { useConflictWebSocket } from "@/hooks/useConflictWebSocket";
import { getApiBase } from "@/lib/api";
import { useUserSettings } from "@/hooks/useUserSettings";
import { useUserProfile } from "@/hooks/useUserProfile";
import { useSavedAnalyses } from "@/hooks/useSavedAnalyses";
import { ChevronDown, Play, LogOut, Menu, X, Radio, Rss, ChevronRight, Star, Save, Trash2, User } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";

const Dashboard = () => {
  const { user, signOut } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [conflictDropdownOpen, setConflictDropdownOpen] = useState(false);
  const conflictDropdownRef = useRef<HTMLDivElement>(null);

  const { settings, setDefaultConflict, toggleFavorite, setUiState, error: settingsError } = useUserSettings();
  const { profile, updateProfile, error: profileError, ensureProfile } = useUserProfile();
  const [profileEditOpen, setProfileEditOpen] = useState(false);
  const [profileDisplayName, setProfileDisplayName] = useState("");
  const accountError = profileError || settingsError;
  const selectedConflict = settings.default_conflict;
  const setSelectedConflict = useCallback(
    (value: string) => {
      setDefaultConflict(value);
    },
    [setDefaultConflict]
  );

  const [leftPanelOpen, setLeftPanelOpen] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [agentExpanded, setAgentExpanded] = useState<string | null>(null);
  const uiRestored = useRef(false);
  useEffect(() => {
    if (uiRestored.current || !settings.ui_state || typeof settings.ui_state !== "object") return;
    const u = settings.ui_state as { leftPanelOpen?: boolean; rightPanelOpen?: boolean; agentExpanded?: string };
    if (typeof u.leftPanelOpen === "boolean") setLeftPanelOpen(u.leftPanelOpen);
    if (typeof u.rightPanelOpen === "boolean") setRightPanelOpen(u.rightPanelOpen);
    if (u.agentExpanded != null) setAgentExpanded(u.agentExpanded);
    uiRestored.current = true;
  }, [settings.ui_state]);
  const uiStateRef = useRef({ leftPanelOpen, rightPanelOpen, agentExpanded });
  uiStateRef.current = { leftPanelOpen, rightPanelOpen, agentExpanded };
  useEffect(() => {
    const t = setTimeout(() => {
      setUiState({ ...uiStateRef.current });
    }, 500);
    return () => clearTimeout(t);
  }, [leftPanelOpen, rightPanelOpen, agentExpanded, setUiState]);

  const { data: conflictData, status: analysisStatus, runAnalysis, lastUpdated, analysisError } = useConflictWebSocket({
    conflict: selectedConflict,
    enabled: true,
  });
  const isAnalyzing = analysisStatus === "analyzing";
  const apiBase = getApiBase();

  const { list: savedList, saveAnalysis, deleteSaved } = useSavedAnalyses();
  const currentOption = CONFLICT_OPTIONS.find((o) => o.apiValue === selectedConflict);
  const displayConflictLabel = currentOption?.label ?? selectedConflict;

  useEffect(() => {
    const onOutside = (e: MouseEvent) => {
      if (conflictDropdownRef.current && !conflictDropdownRef.current.contains(e.target as Node)) setConflictDropdownOpen(false);
    };
    document.addEventListener("click", onOutside);
    return () => document.removeEventListener("click", onOutside);
  }, []);

  useEffect(() => {
    if (profileEditOpen && (profile?.display_name != null || user?.email)) {
      setProfileDisplayName(profile?.display_name ?? user?.email ?? "");
    }
  }, [profileEditOpen, profile?.display_name, user?.email]);

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

  const handleSignOut = async () => {
    await signOut();
  };

  return (
    <div className="h-screen min-h-0 bg-background flex flex-col overflow-hidden">
      {user && accountError && (
        <div className="bg-destructive/15 border-b border-destructive/40 px-3 py-2 text-center text-xs text-destructive flex items-center justify-center gap-2 flex-wrap">
          <span>Profil/Settings: {accountError}</span>
          <span className="text-muted-foreground">→ Klick auf deinen Namen für Anleitung.</span>
        </div>
      )}
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
                    <Star
                      className={`h-3.5 w-3.5 flex-shrink-0 ${settings.favorite_conflicts.includes(opt.apiValue) ? "fill-amber-400 text-amber-500" : "text-muted-foreground"}`}
                      onClick={(e) => { e.stopPropagation(); toggleFavorite(opt.apiValue); }}
                    />
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
              <p className="text-[10px] text-destructive max-w-[200px] text-right" title={analysisError}>
                {analysisError.includes("fetch") || analysisError.includes("Failed") || analysisError.includes("Network")
                  ? `Backend nicht erreichbar (${apiBase}). Backend starten?`
                  : analysisError}
              </p>
            )}
            <Button
              size="sm"
              className="text-xs px-2 sm:px-3"
              disabled={isAnalyzing}
              onClick={() => runAnalysis()}
              title="Letzte Analyse aus dem Cache laden (Automatik alle 10 Min)"
            >
              {isAnalyzing ? (
                <span className="animate-pulse">Laden…</span>
              ) : (
                <>
                  <span className="hidden sm:inline">Aktualisieren</span>
                  <span className="sm:hidden">Refresh</span>
                </>
              )}
            </Button>
          </div>
          {user && (
            <>
              <Popover open={profileEditOpen} onOpenChange={setProfileEditOpen}>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    className="text-xs text-muted-foreground hidden lg:flex items-center gap-1.5 truncate max-w-[160px] hover:text-foreground"
                    title="Profil bearbeiten"
                  >
                    <User className="h-3.5 w-3.5 flex-shrink-0" />
                    <span className="truncate">{profile?.display_name || user?.email}</span>
                  </button>
                </PopoverTrigger>
                <PopoverContent className="w-72" align="end">
                  <div className="space-y-3">
                    <p className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">Profil</p>
                    {accountError && (
                      <div className="rounded bg-destructive/10 border border-destructive/30 p-2 text-xs text-destructive space-y-1">
                        <p className="font-medium">Fehler: {accountError}</p>
                        <p className="text-[10px] text-muted-foreground mt-1">
                          In Supabase SQL Editor ausführen: <code className="bg-muted px-1 rounded text-[10px]">CREATE POLICY &quot;Users can insert own profile&quot; ON public.profiles FOR INSERT WITH CHECK (auth.uid() = id);</code> Dann hier &quot;Profil anlegen&quot; klicken.
                        </p>
                      </div>
                    )}
                    <div className="space-y-2">
                      <label className="text-xs text-muted-foreground">Anzeigename</label>
                      <Input
                        value={profileDisplayName}
                        onChange={(e) => setProfileDisplayName(e.target.value)}
                        placeholder={user?.email ?? ""}
                        className="text-sm h-8"
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        className="text-xs flex-1"
                        onClick={() => {
                          updateProfile({ display_name: profileDisplayName.trim() || undefined });
                          setProfileEditOpen(false);
                        }}
                      >
                        Speichern
                      </Button>
                      <Button size="sm" variant="outline" className="text-xs" onClick={() => setProfileEditOpen(false)}>
                        Abbrechen
                      </Button>
                      {!profile && (
                        <Button size="sm" variant="secondary" className="text-xs w-full" onClick={() => ensureProfile().then((ok) => ok && setProfileEditOpen(false))}>
                          Profil anlegen
                        </Button>
                      )}
                    </div>
                    <p className="text-[10px] text-muted-foreground truncate">Account: {user?.email}</p>
                  </div>
                </PopoverContent>
              </Popover>
              <button onClick={handleSignOut} className="text-muted-foreground hover:text-foreground transition-colors" title="Sign Out">
                <LogOut className="h-4 w-4" />
              </button>
            </>
          )}
        </div>
      </header>

      {/* Mobile menu dropdown */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-b border-border bg-card p-4 space-y-4 animate-fade-in-up">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground truncate">{user?.email}</span>
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
        {/* Left Sidebar - Desktop always visible, mobile as overlay */}
        <aside className={`
          ${leftPanelOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0
          w-56 border-r border-border flex-shrink-0 p-4 overflow-y-auto bg-background
          absolute lg:relative inset-y-0 left-0 z-20
          transition-transform duration-300 ease-in-out
        `}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-mono text-xs text-muted-foreground tracking-wider">AGENT STATUS</h2>
            <button className="lg:hidden text-muted-foreground hover:text-foreground" onClick={() => setLeftPanelOpen(false)}>
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="space-y-1">
            {AGENTS_WITH_SOURCES.map((agent) => (
              <div key={agent.name} className="rounded border border-border/60 bg-card/50 overflow-hidden">
                <button
                  className="w-full flex items-center gap-2 p-2 text-left hover:bg-muted/50 transition-colors"
                  onClick={() => setAgentExpanded(agentExpanded === agent.name ? null : agent.name)}
                >
                  <span className="h-2 w-2 rounded-full flex-shrink-0 bg-primary animate-pulse-dot" />
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-xs font-medium">{agent.name}</div>
                    <div className="text-[10px] text-muted-foreground">{agent.fullName}</div>
                  </div>
                  <ChevronRight
                    className={`h-3 w-3 flex-shrink-0 text-muted-foreground transition-transform ${agentExpanded === agent.name ? "rotate-90" : ""}`}
                  />
                </button>
                {agentExpanded === agent.name && (
                  <div className="border-t border-border/60 px-2 py-2 space-y-1.5 bg-background/50">
                    <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">Data sources</div>
                    {agent.sources.map((src, i) => (
                      <div key={i} className="text-xs">
                        <span className="font-medium text-foreground">{src.name}</span>
                        {src.description && (
                          <p className="text-[10px] text-muted-foreground mt-0.5 leading-tight">{src.description}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </aside>

        {/* Overlay backdrop for mobile panels */}
        {(leftPanelOpen || rightPanelOpen) && (
          <div
            className="lg:hidden absolute inset-0 z-10 bg-background/60 backdrop-blur-sm"
            onClick={() => { setLeftPanelOpen(false); setRightPanelOpen(false); }}
          />
        )}

        {/* Center Map – bleibt oben, nimmt verfügbaren Platz; rechte Spalte scrollt separat */}
        <main className="flex-1 min-h-0 min-w-0 relative overflow-hidden flex flex-col">
          <div className="absolute inset-0 grid-overlay opacity-30" />
          <ConflictMap />

          {/* Mobile floating panel toggles */}
          <div className="absolute top-3 left-3 flex gap-2 lg:hidden z-10">
            <button
              onClick={() => { setLeftPanelOpen(!leftPanelOpen); setRightPanelOpen(false); }}
              className="flex items-center gap-1 rounded border border-border bg-background/90 backdrop-blur-sm px-2 py-1.5 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors"
            >
              <Radio className="h-3 w-3" />
              <span className="hidden sm:inline">Agents</span>
            </button>
          </div>
          <div className="absolute top-3 right-3 flex gap-2 md:hidden z-10">
            <button
              onClick={() => { setRightPanelOpen(!rightPanelOpen); setLeftPanelOpen(false); }}
              className="flex items-center gap-1 rounded border border-border bg-background/90 backdrop-blur-sm px-2 py-1.5 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors"
            >
              <Rss className="h-3 w-3" />
              <span className="hidden sm:inline">Feed</span>
            </button>
          </div>

          {/* Bottom Escalation Timeline */}
          <div className="absolute bottom-0 left-0 right-0 border-t border-border bg-background/90 backdrop-blur-sm p-2 sm:p-3">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] sm:text-xs text-muted-foreground">[ Escalation Timeline ]</span>
              <div className="flex items-center gap-2 sm:gap-4">
                {["06:00", "08:00", "10:00", "12:00", "14:00"].map((t, i) => (
                  <div key={t} className="flex flex-col items-center gap-1">
                    <div className={`h-1.5 w-1.5 sm:h-2 sm:w-2 rounded-full ${i === 4 ? "bg-threat" : i >= 2 ? "bg-warning" : "bg-primary"}`} />
                    <span className="font-mono text-[8px] sm:text-[10px] text-muted-foreground">{t}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </main>

        {/* Right Panel – Iran Monitor style: Daily Briefing, Headlines, Events, Activity, Saved */}
        <aside className={`
          ${rightPanelOpen ? "translate-x-0" : "translate-x-full"}
          md:translate-x-0
          w-72 sm:w-80 border-l border-border flex-shrink-0 p-4 flex flex-col overflow-y-auto bg-background
          absolute md:relative inset-y-0 right-0 z-20
          transition-transform duration-300 ease-in-out
        `}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-mono text-xs text-muted-foreground tracking-wider">INTELLIGENCE FEED</h2>
            <button className="md:hidden text-muted-foreground hover:text-foreground" onClick={() => setRightPanelOpen(false)}>
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-4">
            <DailyBriefing data={conflictData} conflictLabel={displayConflictLabel} lastUpdated={lastUpdated} />
            <LatestHeadlines data={conflictData} maxItems={15} />
            <EventsTimeline data={conflictData} />
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

          {/* Saved analyses (B) */}
          <div className="mt-4 pt-4 border-t border-border">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-mono text-xs text-muted-foreground tracking-wider">SAVED ANALYSES</h3>
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 gap-1"
                disabled={!conflictData || isAnalyzing}
                onClick={() =>
                  conflictData &&
                  saveAnalysis({
                    conflict: selectedConflict,
                    payload: conflictData as unknown as Record<string, unknown>,
                    label: `${displayConflictLabel} – ${new Date().toLocaleDateString()}`,
                  })
                }
              >
                <Save className="h-3 w-3" />
                Save current
              </Button>
            </div>
            <ul className="space-y-2 max-h-48 overflow-y-auto">
              {savedList.length === 0 && (
                <li className="text-xs text-muted-foreground py-2">No saved analyses yet.</li>
              )}
              {savedList.map((s) => (
                <li key={s.id} className="rounded border border-border bg-card/50 p-2 flex items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="font-mono text-xs truncate">{s.label || s.conflict}</div>
                    <div className="text-[10px] text-muted-foreground">
                      {new Date(s.created_at).toLocaleString()}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-destructive flex-shrink-0"
                    onClick={() => deleteSaved(s.id)}
                    title="Delete"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <p className="mt-4 pt-3 border-t border-border text-[10px] text-muted-foreground">
            Data sources: News API · GDELT · RSS · Polymarket · ADSB · VesselFinder · NASA FIRMS · ReliefWeb · Shodan · IODA
          </p>
        </aside>
      </div>
    </div>
  );
};

export default Dashboard;

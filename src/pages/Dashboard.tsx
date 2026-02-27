import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ConflictMap } from "@/components/dashboard/ConflictMap";
import { ChevronDown, Play, LogOut, Menu, X, Radio, Rss } from "lucide-react";

const agents = [
  { name: "GEOINT", status: "Active", updated: "2m ago", active: true },
  { name: "SIGINT", status: "Active", updated: "5m ago", active: true },
  { name: "SOCMINT", status: "Idle", updated: "18m ago", active: false },
  { name: "FININT", status: "Active", updated: "1m ago", active: true },
  { name: "TECHINT", status: "Idle", updated: "32m ago", active: false },
];

const intelFeed = [
  {
    type: "SIGINT",
    confidence: 87,
    time: "14:32 UTC",
    text: "RC-135 Rivet Joint detected over Persian Gulf – 3rd pass in 6 hours",
    source: "ADSB-Exchange",
  },
  {
    type: "FININT",
    confidence: 91,
    time: "14:28 UTC",
    text: "Brent crude +4.2% — highest single-day move in 3 weeks",
    source: "Alpha Vantage",
  },
  {
    type: "SOCMINT",
    confidence: 61,
    time: "14:15 UTC",
    text: "IRGC mobilization reports on 3 Telegram channels",
    source: "Telegram Monitor",
  },
];

const Dashboard = () => {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [leftPanelOpen, setLeftPanelOpen] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);

  const handleSignOut = async () => {
    await signOut();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
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
          <button className="flex items-center gap-1 text-xs sm:text-sm font-mono border border-border rounded px-2 sm:px-3 py-1 hover:bg-secondary transition-colors">
            <span className="hidden sm:inline">US – Iran</span>
            <span className="sm:hidden">US–IR</span>
            <ChevronDown className="h-3 w-3" />
          </button>
          <Badge className="bg-warning/20 text-warning border-warning/30 font-mono text-[10px] sm:text-xs hidden sm:flex">ELEVATED</Badge>
          <Button size="sm" className="text-xs px-2 sm:px-3">
            <span className="hidden sm:inline">Run Analysis</span>
            <span className="sm:hidden">Run</span>
          </Button>
          <span className="text-xs text-muted-foreground hidden lg:inline truncate max-w-[160px]">{user?.email}</span>
          <button onClick={handleSignOut} className="text-muted-foreground hover:text-foreground transition-colors" title="Sign Out">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* Mobile menu dropdown */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-b border-border bg-card p-4 space-y-4 animate-fade-in-up">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground truncate">{user?.email}</span>
            <Badge className="bg-warning/20 text-warning border-warning/30 font-mono text-[10px] sm:hidden">ELEVATED</Badge>
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

      <div className="flex flex-1 overflow-hidden relative">
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
          <div className="space-y-3">
            {agents.map(agent => (
              <div key={agent.name} className="group flex items-center gap-3 text-sm">
                <span className={`h-2 w-2 rounded-full flex-shrink-0 ${agent.active ? "bg-primary animate-pulse-dot" : "bg-muted-foreground"}`} />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-xs font-medium">{agent.name}</div>
                  <div className="text-xs text-muted-foreground">{agent.status} · {agent.updated}</div>
                </div>
                <button className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-primary">
                  <Play className="h-3 w-3" />
                </button>
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

        {/* Center Map */}
        <main className="flex-1 relative overflow-hidden">
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

        {/* Right Panel - Intel Feed */}
        <aside className={`
          ${rightPanelOpen ? "translate-x-0" : "translate-x-full"}
          md:translate-x-0
          w-72 sm:w-80 border-l border-border flex-shrink-0 p-4 flex flex-col overflow-y-auto bg-background
          absolute md:relative inset-y-0 right-0 z-20
          transition-transform duration-300 ease-in-out
        `}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-mono text-xs text-muted-foreground tracking-wider">INTELLIGENCE FEED</h2>
            <button className="md:hidden text-muted-foreground hover:text-foreground" onClick={() => setRightPanelOpen(false)}>
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="space-y-3">
            {intelFeed.map((item, i) => (
              <div key={i} className="rounded-lg border border-border bg-card p-3 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="outline" className="font-mono text-[10px] border-primary/40 text-primary">{item.type}</Badge>
                  <Badge variant="outline" className="font-mono text-[10px]">{item.confidence}% confidence</Badge>
                  <span className="text-[10px] text-muted-foreground ml-auto">{item.time}</span>
                </div>
                <p className="text-sm leading-relaxed">{item.text}</p>
                <p className="text-[10px] text-muted-foreground">Source: {item.source}</p>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
};

export default Dashboard;

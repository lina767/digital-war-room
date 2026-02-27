import { useAuth } from "@/contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ChevronDown, Play, LogOut } from "lucide-react";

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

  const handleSignOut = async () => {
    await signOut();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Top Navbar */}
      <header className="h-14 border-b border-border flex items-center justify-between px-4 flex-shrink-0">
        <div className="font-mono font-bold text-primary text-glow text-sm tracking-wider">
          DIGITAL WAR ROOM
        </div>
        <div className="flex items-center gap-3">
          <button className="flex items-center gap-1 text-sm font-mono border border-border rounded px-3 py-1 hover:bg-secondary transition-colors">
            US – Iran <ChevronDown className="h-3 w-3 ml-1" />
          </button>
          <Badge className="bg-warning/20 text-warning border-warning/30 font-mono text-xs">ELEVATED</Badge>
          <Button size="sm">Run Analysis</Button>
          <span className="text-xs text-muted-foreground hidden md:inline truncate max-w-[160px]">{user?.email}</span>
          <button onClick={handleSignOut} className="text-muted-foreground hover:text-foreground transition-colors" title="Sign Out">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar */}
        <aside className="w-56 border-r border-border flex-shrink-0 p-4 hidden lg:block overflow-y-auto">
          <h2 className="font-mono text-xs text-muted-foreground mb-4 tracking-wider">AGENT STATUS</h2>
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

        {/* Center Map */}
        <main className="flex-1 relative overflow-hidden">
          <div className="absolute inset-0 grid-overlay" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <div className="font-mono text-muted-foreground text-sm border border-border rounded px-4 py-2 bg-card/50">
                [ Interactive Map — Loading... ]
              </div>
            </div>
          </div>

          {/* Bottom Escalation Timeline */}
          <div className="absolute bottom-0 left-0 right-0 border-t border-border bg-background/90 backdrop-blur-sm p-3">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs text-muted-foreground">[ Escalation Timeline ]</span>
              <div className="flex items-center gap-4">
                {["06:00", "08:00", "10:00", "12:00", "14:00"].map((t, i) => (
                  <div key={t} className="flex flex-col items-center gap-1">
                    <div className={`h-2 w-2 rounded-full ${i === 4 ? "bg-threat" : i >= 2 ? "bg-warning" : "bg-primary"}`} />
                    <span className="font-mono text-[10px] text-muted-foreground">{t}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </main>

        {/* Right Panel - Intel Feed */}
        <aside className="w-80 border-l border-border flex-shrink-0 p-4 hidden md:flex flex-col overflow-y-auto">
          <h2 className="font-mono text-xs text-muted-foreground mb-4 tracking-wider">INTELLIGENCE FEED</h2>
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

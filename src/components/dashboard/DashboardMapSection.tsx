import { ReactNode } from "react";
import { ConflictMap } from "@/components/dashboard/ConflictMap";
import { Radio, Rss } from "lucide-react";

interface DashboardMapSectionProps {
  leftPanelOpen: boolean;
  setLeftPanelOpen: (open: boolean) => void;
  rightPanelOpen: boolean;
  setRightPanelOpen: (open: boolean) => void;
}

export function DashboardMapSection({
  leftPanelOpen,
  setLeftPanelOpen,
  rightPanelOpen,
  setRightPanelOpen,
}: DashboardMapSectionProps) {
  return (
    <main className="flex-1 min-h-0 min-w-0 relative overflow-hidden flex flex-col">
      <div className="absolute inset-0 grid-overlay opacity-30" />
      <ConflictMap />

      {/* Mobile floating panel toggles */}
      <div className="absolute top-3 left-3 flex gap-2 lg:hidden z-10">
        <button
          onClick={() => {
            setLeftPanelOpen(!leftPanelOpen);
            setRightPanelOpen(false);
          }}
          className="flex items-center gap-1 rounded border border-border bg-background/90 backdrop-blur-sm px-2 py-1.5 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <Radio className="h-3 w-3" />
          <span className="hidden sm:inline">Agents</span>
        </button>
      </div>
      <div className="absolute top-3 right-3 flex gap-2 md:hidden z-10">
        <button
          onClick={() => {
            setRightPanelOpen(!rightPanelOpen);
            setLeftPanelOpen(false);
          }}
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
                <div
                  className={`h-1.5 w-1.5 sm:h-2 sm:w-2 rounded-full ${
                    i === 4 ? "bg-threat" : i >= 2 ? "bg-warning" : "bg-primary"
                  }`}
                />
                <span className="font-mono text-[8px] sm:text-[10px] text-muted-foreground">{t}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}


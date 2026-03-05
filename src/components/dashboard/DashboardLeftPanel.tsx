import { ChevronRight, X } from "lucide-react";
import { AGENTS_WITH_SOURCES } from "@/components/dashboard/agentsConfig";
import { Dispatch, SetStateAction } from "react";

interface DashboardLeftPanelProps {
  leftPanelOpen: boolean;
  setLeftPanelOpen: Dispatch<SetStateAction<boolean>>;
  agentExpanded: string | null;
  setAgentExpanded: Dispatch<SetStateAction<string | null>>;
}

export function DashboardLeftPanel({
  leftPanelOpen,
  setLeftPanelOpen,
  agentExpanded,
  setAgentExpanded,
}: DashboardLeftPanelProps) {
  return (
    <aside
      className={`
          ${leftPanelOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0
          w-56 border-r border-border flex-shrink-0 p-4 overflow-y-auto bg-background
          absolute lg:relative inset-y-0 left-0 z-20
          transition-transform duration-300 ease-in-out
        `}
    >
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
                className={`h-3 w-3 flex-shrink-0 text-muted-foreground transition-transform ${
                  agentExpanded === agent.name ? "rotate-90" : ""
                }`}
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
  );
}


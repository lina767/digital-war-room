import { ChevronRight, AlertTriangle, X } from "lucide-react";
import { AGENTS_WITH_SOURCES, AGENT_NAME_TO_KEY } from "@/components/dashboard/agentsConfig";
import { Dispatch, SetStateAction } from "react";
import type { ConflictData } from "@/types/conflict";
import { FindingConfidenceBadge } from "@/components/dashboard/FindingConfidenceBadge";
import { getAgentConfidenceFromConflict, type DataQualityLevel } from "@/components/dashboard/agentConfidenceHelpers";
import { Badge } from "@/components/ui/badge";
import { ErrorBoundary } from "@/components/ErrorBoundary";

const DATA_QUALITY_STYLES: Record<DataQualityLevel, string> = {
  live: "bg-emerald-500/15 text-emerald-300 border-emerald-500/35",
  estimated: "bg-amber-500/15 text-amber-200 border-amber-500/35",
  degraded: "bg-destructive/15 text-destructive/90 border-destructive/35",
};

function DataQualityBadge({ level }: { level: DataQualityLevel }) {
  return (
    <Badge
      variant="outline"
      className={`text-[9px] font-mono uppercase tracking-wide px-1.5 py-0 h-5 shrink-0 ${DATA_QUALITY_STYLES[level]}`}
      title={`Data quality (feed): ${level}`}
    >
      {level}
    </Badge>
  );
}

interface DashboardLeftPanelProps {
  leftPanelOpen: boolean;
  setLeftPanelOpen: Dispatch<SetStateAction<boolean>>;
  agentExpanded: string | null;
  setAgentExpanded: Dispatch<SetStateAction<string | null>>;
  /** When present, agent status dots reflect timeout_or_error from last analysis run. */
  conflictData?: ConflictData | null;
}

export function DashboardLeftPanel({
  leftPanelOpen,
  setLeftPanelOpen,
  agentExpanded,
  setAgentExpanded,
  conflictData,
}: DashboardLeftPanelProps) {
  const getAgentStatus = (agentName: string): "ok" | "error" => {
    if (!conflictData) return "ok";
    const key = AGENT_NAME_TO_KEY[agentName];
    if (!key) return "ok";
    const agentResult = (conflictData as Record<string, { timeout_or_error?: boolean } | undefined>)[key];
    return agentResult?.timeout_or_error === true ? "error" : "ok";
  };

  return (
    <aside
      className={`
          ${leftPanelOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0
          w-[min(14rem,85vw)] sm:w-56 border-r border-border flex-shrink-0 p-4 overflow-y-auto overscroll-contain bg-background
          absolute lg:relative inset-y-0 left-0 z-20
          transition-transform duration-300 ease-in-out
        `}
      aria-label="Agent status and data sources"
    >
      <div className="flex items-center justify-between mb-4 gap-2">
        <div className="min-w-0">
          <h2 className="font-mono text-xs text-muted-foreground tracking-wider truncate">AGENT STATUS</h2>
          <p className="text-[10px] text-muted-foreground/80 leading-tight mt-0.5">
            Score = source health · Data = feed quality
          </p>
        </div>
        <button
          type="button"
          aria-label="Close panel"
          className="lg:hidden min-h-11 min-w-11 flex items-center justify-center -m-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 active:bg-muted touch-manipulation"
          onClick={() => setLeftPanelOpen(false)}
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>
      <div className="space-y-2">
        {AGENTS_WITH_SOURCES.map((agent) => {
          const status = getAgentStatus(agent.name);
          const agentKey = AGENT_NAME_TO_KEY[agent.name] ?? agent.name.replace(/\s+/g, "-").toLowerCase();
          const sourcesPanelId = `agent-sources-${agentKey}`;
          const { scoreLevel, dataQuality, tooltip } = getAgentConfidenceFromConflict(conflictData, agentKey);
          return (
            <ErrorBoundary sectionLabel={`${agent.name} Panel`}>
              <div className="rounded-md border border-border/60 bg-card/50 overflow-hidden">
                <button
                  type="button"
                  aria-expanded={agentExpanded === agent.name}
                  aria-controls={agentExpanded === agent.name ? sourcesPanelId : undefined}
                  className="w-full flex items-center gap-2 p-3 sm:p-2 text-left hover:bg-muted/50 active:bg-muted/50 transition-colors touch-manipulation min-h-11 sm:min-h-0"
                  onClick={() => setAgentExpanded(agentExpanded === agent.name ? null : agent.name)}
                  title={
                    status === "error"
                      ? "Agent failed or timed out – data may be stale"
                      : tooltip || "Expand for data sources"
                  }
                >
                  {status === "error" ? (
                    <span className="h-2 w-2 rounded-full flex-shrink-0 bg-destructive" aria-hidden />
                  ) : (
                    <span className="h-2 w-2 rounded-full flex-shrink-0 bg-primary animate-pulse-dot" aria-hidden />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-xs font-medium truncate">{agent.name}</div>
                    <div className="text-[11px] text-muted-foreground line-clamp-2">
                      {status === "error" ? "Error / timeout – stale data" : agent.fullName}
                    </div>
                    {(scoreLevel || dataQuality) && status !== "error" && (
                      <div className="flex flex-wrap items-center gap-1 mt-1.5">
                        {scoreLevel && <FindingConfidenceBadge level={scoreLevel} />}
                        {dataQuality && <DataQualityBadge level={dataQuality} />}
                      </div>
                    )}
                  </div>
                  <ChevronRight
                    className={`h-3 w-3 flex-shrink-0 text-muted-foreground transition-transform ${
                      agentExpanded === agent.name ? "rotate-90" : ""
                    }`}
                    aria-hidden
                  />
                </button>
                {agentExpanded === agent.name && (
                  <div id={sourcesPanelId} role="region" className="border-t border-border/60 px-2 py-2 space-y-1.5 bg-background/50" aria-label={`${agent.name} data sources`}>
                    {status === "error" && (
                      <div className="flex items-center gap-1.5 text-destructive text-[11px]">
                        <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden />
                        <span>This agent failed or timed out. Data may be from a previous run.</span>
                      </div>
                    )}
                    {tooltip && (
                      <p className="text-[10px] text-muted-foreground leading-snug font-mono">{tooltip}</p>
                    )}
                    <div className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">Data sources</div>
                    {agent.sources.map((src, i) => (
                      <div key={i} className="text-xs">
                        <span className="font-medium text-foreground">{src.name}</span>
                        {src.description && (
                          <p className="text-[11px] text-muted-foreground mt-0.5 leading-tight">{src.description}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </ErrorBoundary>
          );
        })}
      </div>
    </aside>
  );
}


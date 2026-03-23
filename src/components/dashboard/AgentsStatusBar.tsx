import { useState, useEffect } from "react";
import { getAgentsStatus } from "@/lib/api";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

/** GET /api/agents/status returns { finint: { status: "ok"|"error", ... } | "ok"|"error", ... } */
function agentStatusValue(v: unknown): string {
  if (typeof v === "object" && v !== null && "status" in v) return (v as { status: string }).status;
  return typeof v === "string" ? v : "ok";
}

function confidenceSummary(v: unknown): string | null {
  if (typeof v !== "object" || v === null) return null;
  const o = v as Record<string, unknown>;
  const conf = o.confidence;
  if (!conf || typeof conf !== "object") return null;
  const level = (conf as { level?: string }).level;
  const dc = o.data_confidence;
  const parts: string[] = [];
  if (level) parts.push(`sources ${level}`);
  if (typeof dc === "string" && dc) parts.push(`data ${dc}`);
  return parts.length ? parts.join(" · ") : null;
}

export function AgentsStatusBar() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAgentsStatus().then((data) => {
      if (!cancelled && data && typeof data === "object") setStatus(data);
    });
    return () => { cancelled = true; };
  }, []);

  if (!status || Object.keys(status).length === 0) return null;

  const entries = Object.entries(status);
  const okCount = entries.filter(([, v]) => agentStatusValue(v) === "ok").length;
  const errorCount = entries.filter(([, v]) => agentStatusValue(v) === "error").length;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1 flex-wrap text-[10px] font-mono text-muted-foreground cursor-help">
            {entries.map(([key, value]) => {
              const s = agentStatusValue(value);
              return (
                <span
                  key={key}
                  className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
                    s === "ok" ? "bg-emerald-500/80" : "bg-destructive/80"
                  }`}
                  title={`${key}: ${s}`}
                />
              );
            })}
            <span className="ml-0.5">
              {okCount}/{entries.length}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[240px] text-xs">
          <p className="font-mono text-[10px] text-muted-foreground uppercase mb-1">Agents (last run)</p>
          <ul className="space-y-0.5">
            {entries.map(([key, value]) => {
              const s = agentStatusValue(value);
              const confLine = confidenceSummary(value);
              return (
                <li key={key} className="space-y-0.5">
                  <div className="flex justify-between gap-2">
                    <span>{key}</span>
                    <span className={s === "ok" ? "text-emerald-400" : "text-destructive"}>{s}</span>
                  </div>
                  {confLine && (
                    <p className="text-[10px] text-muted-foreground pl-0 font-mono">{confLine}</p>
                  )}
                </li>
              );
            })}
          </ul>
          {errorCount > 0 && (
            <p className="text-[10px] text-destructive mt-1">{errorCount} agent(s) had errors in last run.</p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

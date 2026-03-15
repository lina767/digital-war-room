import { useState, useEffect } from "react";
import { getApiBase } from "@/lib/api";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

/** GET /api/agents/status returns { finint: "ok"|"error", news: "ok", ... } */
export function AgentsStatusBar() {
  const [status, setStatus] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${getApiBase()}/api/agents/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: Record<string, string> | null) => {
        if (!cancelled && data && typeof data === "object") setStatus(data);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  if (!status || Object.keys(status).length === 0) return null;

  const entries = Object.entries(status);
  const okCount = entries.filter(([, v]) => v === "ok").length;
  const errorCount = entries.filter(([, v]) => v === "error").length;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1 flex-wrap text-[10px] font-mono text-muted-foreground cursor-help">
            {entries.map(([key, value]) => (
              <span
                key={key}
                className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
                  value === "ok" ? "bg-emerald-500/80" : "bg-destructive/80"
                }`}
                title={`${key}: ${value}`}
              />
            ))}
            <span className="ml-0.5">
              {okCount}/{entries.length}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[240px] text-xs">
          <p className="font-mono text-[10px] text-muted-foreground uppercase mb-1">Agents (last run)</p>
          <ul className="space-y-0.5">
            {entries.map(([key, value]) => (
              <li key={key} className="flex justify-between gap-2">
                <span>{key}</span>
                <span className={value === "ok" ? "text-emerald-400" : "text-destructive"}>{value}</span>
              </li>
            ))}
          </ul>
          {errorCount > 0 && (
            <p className="text-[10px] text-destructive mt-1">{errorCount} agent(s) had errors in last run.</p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

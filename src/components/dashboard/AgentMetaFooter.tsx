import { Badge } from "@/components/ui/badge";
import type { AgentMeta } from "@/lib/api";
import { AlertTriangle, Clock } from "lucide-react";

function formatRelative(iso?: string): string {
  if (!iso) return "–";
  try {
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return "–";
  }
}

interface AgentMetaFooterProps {
  meta?: AgentMeta | null;
  className?: string;
}

/** Small footer for dashboard panels: fetched_at, confidence, source count, staleness/fallback warning. */
export function AgentMetaFooter({ meta, className = "" }: AgentMetaFooterProps) {
  if (!meta) return null;

  const okCount = meta.sources?.filter((s) => s.status === "ok").length ?? 0;
  const total = meta.sources?.length ?? 0;
  const isStale = meta.data_freshness === "stale" || meta.data_freshness === "unavailable";
  const showWarning = meta.fallback_used || isStale;

  return (
    <div className={`flex flex-wrap items-center gap-2 pt-1.5 border-t border-border/50 text-[11px] text-muted-foreground ${className}`}>
      <span className="flex items-center gap-1">
        <Clock className="h-2.5 w-2.5" />
        {formatRelative(meta.fetched_at)}
      </span>
      {meta.confidence?.level && (
        <Badge variant="secondary" className="text-[10px] font-normal">
          {meta.confidence.level}
        </Badge>
      )}
      {total > 0 && (
        <span>
          {okCount}/{total} sources ok
        </span>
      )}
      {showWarning && (
        <span className="flex items-center gap-1 text-amber-500" title={meta.error_summary ?? undefined}>
          <AlertTriangle className="h-2.5 w-2.5" />
          {meta.fallback_used ? "fallback" : meta.data_freshness}
        </span>
      )}
    </div>
  );
}

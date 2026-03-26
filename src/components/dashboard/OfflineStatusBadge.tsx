import { Wifi, WifiOff, CloudOff, Database } from "lucide-react";
import type { ConnectionStatus } from "@/types/conflict";
import { formatTimeAgo } from "@/lib/utils";

interface OfflineStatusBadgeProps {
  isOffline: boolean;
  lastUpdated: Date | null;
  wsStatus: ConnectionStatus;
  /** True when current data was loaded from IndexedDB cache (e.g. after fetch failed or offline). */
  dataFromCache?: boolean;
  compact?: boolean;
}

export function OfflineStatusBadge({
  isOffline,
  lastUpdated,
  wsStatus,
  dataFromCache = false,
  compact = false,
}: OfflineStatusBadgeProps) {
  const syncedText = lastUpdated ? formatTimeAgo(lastUpdated) : "No sync yet";
  const showCachedHint = dataFromCache && (isOffline || !compact);

  if (isOffline) {
    return (
      <div className="inline-flex flex-col gap-1">
        <div
          className="inline-flex items-center gap-1.5 rounded border border-warning/40 bg-warning/10 px-2 py-1 text-[11px] font-mono text-warning"
          title={`Offline mode. Last synced ${syncedText}.`}
        >
          <WifiOff className="h-3.5 w-3.5" aria-hidden />
          <span>Offline</span>
          {!compact && <span className="text-muted-foreground">· last synced {syncedText}</span>}
        </div>
        {showCachedHint && (
          <span className="text-[10px] font-mono text-muted-foreground flex items-center gap-1" title="Data from local cache (IndexedDB).">
            <Database className="h-3 w-3" aria-hidden />
            Serving cached data
          </span>
        )}
      </div>
    );
  }

  if (wsStatus === "connected" || wsStatus === "analyzing") {
    return (
      <div className="inline-flex flex-col gap-1">
        <div
          className="inline-flex items-center gap-1.5 rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-[11px] font-mono text-emerald-400"
          title={lastUpdated ? `Online. Last synced ${syncedText}.` : "Online. Waiting for first sync."}
        >
          <Wifi className="h-3.5 w-3.5" aria-hidden />
          <span>Online</span>
          {!compact && <span className="text-muted-foreground">· last synced {syncedText}</span>}
        </div>
        {showCachedHint && (
          <span className="text-[10px] font-mono text-muted-foreground flex items-center gap-1" title="Data from local cache (IndexedDB).">
            <Database className="h-3 w-3" aria-hidden />
            Serving cached data
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="inline-flex flex-col gap-1">
      <div
        className="inline-flex items-center gap-1.5 rounded border border-border bg-card/40 px-2 py-1 text-[11px] font-mono text-muted-foreground"
        title={lastUpdated ? `Reconnecting. Last synced ${syncedText}.` : "Reconnecting."}
      >
        <CloudOff className="h-3.5 w-3.5" aria-hidden />
        <span>Syncing…</span>
        {!compact && <span>· last synced {syncedText}</span>}
      </div>
      {showCachedHint && (
        <span className="text-[10px] font-mono text-muted-foreground flex items-center gap-1" title="Data from local cache (IndexedDB).">
          <Database className="h-3 w-3" aria-hidden />
          Serving cached data
        </span>
      )}
    </div>
  );
}

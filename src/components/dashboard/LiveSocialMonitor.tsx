import { IntelPanel } from "@/components/dashboard/IntelPanel";
import type { SocialSignal } from "@/hooks/useSocialWebSocket";
import { formatTimeAgo } from "@/lib/utils";

interface LiveSocialMonitorProps {
  status: "connecting" | "connected" | "disconnected" | "error";
  error: string | null;
  lastUpdated: Date | null;
  twitter: SocialSignal[];
  telegram: SocialSignal[];
  reddit: SocialSignal[];
}

function SignalList({ items, emptyText }: { items: SocialSignal[]; emptyText: string }) {
  if (!items.length) return <p className="text-[11px] text-muted-foreground italic">{emptyText}</p>;
  return (
    <ul className="space-y-1.5">
      {items.slice(0, 3).map((item, idx) => {
        const text = item.text || item.title || "Untitled";
        return (
          <li key={`${item.source ?? "source"}-${idx}`} className="text-xs leading-snug">
            <a
              href={item.url || "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary transition-colors"
            >
              {text.length > 100 ? `${text.slice(0, 100)}...` : text}
            </a>
          </li>
        );
      })}
    </ul>
  );
}

export function LiveSocialMonitor({
  status,
  error,
  lastUpdated,
  twitter,
  telegram,
  reddit,
}: LiveSocialMonitorProps) {
  return (
    <IntelPanel
      title="LIVE SOCIAL MONITOR"
      headerRight={
        <span className="text-[11px] text-muted-foreground">
          {status === "connected" && lastUpdated ? `${formatTimeAgo(lastUpdated)} ago` : status}
        </span>
      }
      tooltipContent="Live SOCMINT stream over WebSocket (Twitter/X, Telegram, Reddit), refreshed automatically."
    >
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="space-y-2">
        <div>
          <p className="text-[11px] font-mono text-muted-foreground mb-1">TWITTER/X</p>
          <SignalList items={twitter} emptyText="No live Twitter/X signals." />
        </div>
        <div>
          <p className="text-[11px] font-mono text-muted-foreground mb-1">TELEGRAM</p>
          <SignalList items={telegram} emptyText="No live Telegram signals." />
        </div>
        <div>
          <p className="text-[11px] font-mono text-muted-foreground mb-1">REDDIT</p>
          <SignalList items={reddit} emptyText="No live Reddit signals." />
        </div>
      </div>
    </IntelPanel>
  );
}

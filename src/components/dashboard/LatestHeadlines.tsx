import { useState } from "react";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { AgentMetaFooter } from "@/components/dashboard/AgentMetaFooter";
import { formatTimeAgo } from "@/lib/utils";
import { DASHBOARD_PANEL_TOOLTIPS } from "@/lib/dashboardPanelCopy";
import { ChevronDown } from "lucide-react";

const DEFAULT_VISIBLE = 5;
const MAX_VISIBLE = 15;

interface LatestHeadlinesProps {
  data: ConflictData | null;
  maxItems?: number;
}

export function LatestHeadlines({ data, maxItems = DEFAULT_VISIBLE }: LatestHeadlinesProps) {
  const articles = data?.news?.articles ?? [];
  const [showAll, setShowAll] = useState(false);
  const visibleCount = showAll ? Math.min(articles.length, MAX_VISIBLE) : Math.min(articles.length, maxItems);
  const display = articles.slice(0, visibleCount);
  const hasMore = articles.length > visibleCount;

  return (
    <IntelPanel
      title="LATEST HEADLINES"
      headerRight={articles.length > 0 ? <span className="text-[11px] text-muted-foreground">{articles.length} stories</span> : undefined}
      tooltipContent={DASHBOARD_PANEL_TOOLTIPS["LATEST HEADLINES"]}
    >
      <ul className="divide-y divide-border/60 max-h-64 overflow-y-auto">
        {display.length === 0 && (
          <li className="px-3 py-4 text-xs text-muted-foreground italic">Run analysis to load headlines.</li>
        )}
        {display.map((art, i) => (
          <li key={art.url ?? art.title ?? `headline-${i}`} className="px-3 py-2 hover:bg-muted/30 transition-colors">
            <a
              href={art.url || "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-xs leading-snug text-foreground hover:text-primary"
            >
              {art.title || "Untitled"}
            </a>
            <div className="flex items-center gap-2 mt-1 text-[11px] text-muted-foreground">
              {art.source && <span>{art.source}</span>}
              {(art.source || art.publishedAt) && <span>·</span>}
              {art.publishedAt && <span>{formatTimeAgo(art.publishedAt, false)} ago</span>}
            </div>
          </li>
        ))}
      </ul>
      {hasMore && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="w-full px-3 py-2 text-[11px] font-mono text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors flex items-center justify-center gap-1"
        >
          <ChevronDown className="h-3 w-3" />
          Show more ({articles.length - visibleCount} more)
        </button>
      )}
      <AgentMetaFooter meta={data?.news?._meta} />
    </IntelPanel>
  );
}

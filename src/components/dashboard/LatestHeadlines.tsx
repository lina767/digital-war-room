import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { formatTimeAgo } from "@/lib/utils";

interface LatestHeadlinesProps {
  data: ConflictData | null;
  maxItems?: number;
}

export function LatestHeadlines({ data, maxItems = 15 }: LatestHeadlinesProps) {
  const articles = data?.news?.articles ?? [];
  const display = articles.slice(0, maxItems);

  return (
    <IntelPanel
      title="LATEST HEADLINES"
      headerRight={articles.length > 0 ? <span className="text-[11px] text-muted-foreground">{articles.length} stories</span> : undefined}
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
    </IntelPanel>
  );
}

import type { ConflictData } from "@/hooks/useConflictWebSocket";

interface LatestHeadlinesProps {
  data: ConflictData | null;
  maxItems?: number;
}

function formatArticleTime(publishedAt?: string): string {
  if (!publishedAt) return "";
  try {
    const d = new Date(publishedAt);
    const sec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (sec < 60) return "Just now";
    if (sec < 3600) return `${Math.floor(sec / 60)}m`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
    return `${Math.floor(sec / 86400)}d`;
  } catch {
    return "";
  }
}

export function LatestHeadlines({ data, maxItems = 15 }: LatestHeadlinesProps) {
  const articles = data?.news?.articles ?? [];
  const display = articles.slice(0, maxItems);

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-muted/30 flex items-center justify-between">
        <h3 className="font-mono text-xs text-muted-foreground tracking-wider">LATEST HEADLINES</h3>
        {articles.length > 0 && (
          <span className="text-[10px] text-muted-foreground">{articles.length} stories</span>
        )}
      </div>
      <ul className="divide-y divide-border/60 max-h-64 overflow-y-auto">
        {display.length === 0 && (
          <li className="px-3 py-4 text-xs text-muted-foreground italic">Run analysis to load headlines.</li>
        )}
        {display.map((art, i) => (
          <li key={i} className="px-3 py-2 hover:bg-muted/30 transition-colors">
            <a
              href={art.url || "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-xs leading-snug text-foreground hover:text-primary"
            >
              {art.title || "Untitled"}
            </a>
            <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
              {art.source && <span>{art.source}</span>}
              {(art.source || art.publishedAt) && <span>·</span>}
              {art.publishedAt && <span>{formatArticleTime(art.publishedAt)} ago</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

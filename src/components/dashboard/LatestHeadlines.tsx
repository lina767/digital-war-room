import { useMemo, useState } from "react";
import type { ConflictData } from "@/types/conflict";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { AgentMetaFooter } from "@/components/dashboard/AgentMetaFooter";
import { formatTimeAgo } from "@/lib/utils";
import { DASHBOARD_PANEL_TOOLTIPS } from "@/lib/dashboardPanelCopy";
import {
  collectDistinctSourceKeys,
  filterArticlesBySourceKeys,
  filterKeysToMajorWires,
  headlineSourceKey,
} from "@/lib/headlineSources";
import { ChevronDown, Filter } from "lucide-react";

const DEFAULT_VISIBLE = 5;
const MAX_VISIBLE = 15;
const EMPTY_SOURCE_KEYS = new Set<string>();

interface LatestHeadlinesProps {
  data: ConflictData | null;
  maxItems?: number;
  embedded?: boolean;
  /** Empty set = show all sources. Non-empty = only matching sources. */
  allowedSourceKeys?: Set<string>;
  onAllowedSourceKeysChange?: (next: Set<string>) => void;
}

export function LatestHeadlines({
  data,
  maxItems = DEFAULT_VISIBLE,
  embedded = false,
  allowedSourceKeys,
  onAllowedSourceKeysChange,
}: LatestHeadlinesProps) {
  const rawArticles = useMemo(() => data?.news?.articles ?? [], [data?.news?.articles]);
  const sourceKeys = useMemo(() => collectDistinctSourceKeys(rawArticles), [rawArticles]);
  const allowed = allowedSourceKeys ?? EMPTY_SOURCE_KEYS;
  const articles = useMemo(
    () => filterArticlesBySourceKeys(rawArticles, allowed),
    [rawArticles, allowed],
  );
  const filterActive = onAllowedSourceKeysChange != null && allowed.size > 0;
  const [showAll, setShowAll] = useState(false);
  const visibleCount = showAll ? Math.min(articles.length, MAX_VISIBLE) : Math.min(articles.length, maxItems);
  const display = articles.slice(0, visibleCount);
  const hasMore = articles.length > visibleCount;

  const toggleSource = (key: string) => {
    if (!onAllowedSourceKeysChange) return;
    if (allowed.size === 0) {
      onAllowedSourceKeysChange(new Set([key]));
      return;
    }
    const next = new Set(allowed);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onAllowedSourceKeysChange(next);
  };

  const applyMajorWires = () => {
    if (!onAllowedSourceKeysChange) return;
    const keys = filterKeysToMajorWires(sourceKeys);
    if (keys.length > 0) onAllowedSourceKeysChange(new Set(keys));
  };

  const clearSources = () => onAllowedSourceKeysChange?.(new Set());

  return (
    <IntelPanel
      title="LATEST HEADLINES"
      headerRight={articles.length > 0 ? <span className="text-[11px] text-muted-foreground">{articles.length} stories</span> : undefined}
      tooltipContent={DASHBOARD_PANEL_TOOLTIPS["LATEST HEADLINES"]}
      embedded={embedded}
    >
      {onAllowedSourceKeysChange && sourceKeys.length > 1 && (
        <div className="px-3 pt-2 pb-1 space-y-2 border-b border-border/50">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="flex items-center gap-1 font-mono text-[10px] text-muted-foreground tracking-wider">
              <Filter className="h-3 w-3" aria-hidden />
              SOURCES
            </span>
            <div className="flex items-center gap-1.5 flex-wrap justify-end">
              <button
                type="button"
                onClick={applyMajorWires}
                aria-label="Filter headlines to major wire services"
                className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-border/80 hover:bg-muted/50 text-muted-foreground hover:text-foreground"
              >
                Major wires
              </button>
              <button
                type="button"
                onClick={clearSources}
                disabled={!filterActive}
                aria-label="Show headlines from all sources"
                className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-border/80 hover:bg-muted/50 text-muted-foreground hover:text-foreground disabled:opacity-40 disabled:pointer-events-none"
              >
                All
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {sourceKeys.map((key) => {
              const active = allowed.size === 0 || allowed.has(key);
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => toggleSource(key)}
                  aria-pressed={filterActive ? active : undefined}
                  aria-label={`Toggle headline source ${key}`}
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full border transition-colors ${
                    filterActive && active
                      ? "border-primary/60 bg-primary/15 text-foreground"
                      : filterActive && !active
                        ? "border-border/40 text-muted-foreground/70 hover:border-border"
                        : "border-border/60 text-muted-foreground hover:border-border hover:text-foreground"
                  }`}
                >
                  {key}
                </button>
              );
            })}
          </div>
        </div>
      )}
      <ul className="divide-y divide-border/60 max-h-64 overflow-y-auto">
        {display.length === 0 && (
          <li className="px-3 py-4 text-xs text-muted-foreground italic">Run analysis to load headlines.</li>
        )}
        {display.map((art, i) => (
          <li key={`${headlineSourceKey(art.source)}-${art.url ?? art.title ?? `headline-${i}`}`} className="px-3 py-2 hover:bg-muted/30 transition-colors">
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
          aria-label={`Show ${articles.length - visibleCount} more headlines`}
          className="w-full px-3 py-2 text-[11px] font-mono text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors flex items-center justify-center gap-1"
        >
          <ChevronDown className="h-3 w-3" aria-hidden />
          Show more ({articles.length - visibleCount} more)
        </button>
      )}
      <AgentMetaFooter meta={data?.news?._meta} />
    </IntelPanel>
  );
}

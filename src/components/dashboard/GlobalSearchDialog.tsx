import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Search, X } from "lucide-react";
import { filterSearchHits, type SearchHit } from "@/lib/dashboardSearchIndex";

interface GlobalSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  hits: SearchHit[];
}

function groupLabel(cat: SearchHit["category"]): string {
  if (cat === "finding") return "Findings & scenarios";
  if (cat === "headline") return "Headlines";
  return "Agents & streams";
}

export function GlobalSearchDialog({ open, onOpenChange, hits }: GlobalSearchDialogProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      return;
    }
    const t = window.setTimeout(() => inputRef.current?.focus(), 10);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onOpenChange(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const filtered = useMemo(() => filterSearchHits(hits, query), [hits, query]);

  const grouped = useMemo(() => {
    const order: SearchHit["category"][] = ["finding", "headline", "agent"];
    const map = new Map<SearchHit["category"], SearchHit[]>();
    for (const c of order) map.set(c, []);
    for (const h of filtered) {
      map.get(h.category)?.push(h);
    }
    return order.map((c) => ({ category: c, items: map.get(c) ?? [] })).filter((g) => g.items.length > 0);
  }, [filtered]);

  const onSelect = (h: SearchHit) => {
    if (h.url) {
      window.open(h.url, "_blank", "noopener,noreferrer");
    }
    onOpenChange(false);
  };

  if (!open) return null;

  const node = (
    <div
      className="fixed inset-0 z-[200] flex items-start justify-center p-4 pt-[12vh] bg-black/50 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="global-search-heading"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false);
      }}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-border bg-background shadow-xl overflow-hidden"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <h2 id="global-search-heading" className="sr-only">
            Search findings, headlines, and agents
          </h2>
          <Search className="h-4 w-4 text-muted-foreground flex-shrink-0" aria-hidden />
          <input
            ref={inputRef}
            type="search"
            aria-label="Search query"
            autoComplete="off"
            placeholder="Search findings, headlines, agents…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 min-w-0 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <button
            type="button"
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted"
            aria-label="Close search"
            onClick={() => onOpenChange(false)}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div
          className="max-h-[min(60vh,420px)] overflow-y-auto overscroll-contain text-sm"
          role="region"
          aria-label="Search results"
        >
          {filtered.length === 0 && (
            <p className="px-3 py-6 text-muted-foreground text-center text-xs" role="status">
              No matches.
            </p>
          )}
          {grouped.map((g) => (
            <div key={g.category} className="border-b border-border/60 last:border-0">
              <p className="px-3 pt-2 pb-1 font-mono text-[10px] text-muted-foreground tracking-wider">
                {groupLabel(g.category)}
              </p>
              <ul className="pb-2">
                {g.items.map((h) => (
                  <li key={h.id}>
                    <button
                      type="button"
                      className="w-full text-left px-3 py-2 hover:bg-muted/60 transition-colors rounded-none"
                      onClick={() => onSelect(h)}
                    >
                      <span className="block text-foreground leading-snug">{h.title}</span>
                      <span className="block text-[11px] text-muted-foreground mt-0.5 line-clamp-2">{h.snippet}</span>
                      {h.meta && (
                        <span className="block text-[10px] text-muted-foreground/90 font-mono mt-1">{h.meta}</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="px-3 py-2 border-t border-border bg-muted/20 text-[10px] text-muted-foreground font-mono flex justify-between gap-2">
          <span>Esc to close</span>
          <span>{hits.length} indexed</span>
        </div>
      </div>
    </div>
  );

  return createPortal(node, document.body);
}

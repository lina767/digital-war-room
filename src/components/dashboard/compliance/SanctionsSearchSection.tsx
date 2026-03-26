import { useRef, useState } from "react";
import { Search, Download } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { getApiBase } from "@/lib/api";
import { MATCH_LEVEL_LABELS } from "@/lib/complianceCopy";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { MATCH_LEVEL_STYLES, type SanctionsBatchResult, type SanctionsResponse } from "./shared";

export function SanctionsSearchSection({ data }: { data: ConflictData | null }) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SanctionsResponse | null>(null);
  const [batchResults, setBatchResults] = useState<SanctionsBatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const actorNames = (data?.actors ?? []).map((a) => a.name).filter(Boolean);
  const canScreenActors = actorNames.length > 0;

  async function runSingleSearch(q: string, signal?: AbortSignal): Promise<SanctionsResponse> {
    const base = getApiBase();
    const resp = await fetch(`${base}/api/compliance/sanctions-check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q.trim(), include_ownership_chains: true }),
      signal,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;
    setLoading(true);
    setError(null);
    setResults(null);
    setBatchResults(null);
    try {
      const resultData = await runSingleSearch(query.trim(), signal);
      setResults(resultData);
    } catch (err: unknown) {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleScreenAllActors() {
    if (!canScreenActors) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;
    setLoading(true);
    setError(null);
    setResults(null);
    setBatchResults(null);
    const base = getApiBase();
    try {
      const resp = await fetch(`${base}/api/compliance/sanctions-check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ queries: actorNames, include_ownership_chains: true }),
        signal,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const batchData: SanctionsBatchResult = await resp.json();
      setBatchResults(batchData);
    } catch (err: unknown) {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  function handleExport() {
    const payload = batchResults
      ? { batch: batchResults, exported_at: new Date().toISOString() }
      : results
        ? { single: results, exported_at: new Date().toISOString() }
        : null;
    if (!payload) return;
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sanctions-check-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const hasResults = results != null || batchResults != null;

  return (
    <div className="space-y-2">
      <form onSubmit={handleSearch} className="flex gap-1.5" role="search" aria-label="Sanctions screening">
        <input
          type="text"
          placeholder="Firm or partner name..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Screen firm or partner name against sanctions lists"
          className="flex-1 rounded border border-border bg-background px-2 py-1 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          aria-label="Run sanctions check"
          className="rounded border border-border bg-primary/10 px-2 py-1 text-xs font-mono hover:bg-primary/20 disabled:opacity-50 flex items-center gap-1"
        >
          <Search className="h-3 w-3" />
          {loading ? "..." : "Check"}
        </button>
        {canScreenActors && (
          <button
            type="button"
            onClick={handleScreenAllActors}
            disabled={loading}
            aria-label="Screen all conflict actors"
            title="Conflict actors available for Iran only."
            className="rounded border border-border bg-muted/50 px-2 py-1 text-xs font-mono hover:bg-muted disabled:opacity-50"
          >
            Screen all actors
          </button>
        )}
      </form>

      {error && (
        <div className="flex items-center gap-2">
          <p className="text-[11px] text-destructive">{error}</p>
          <button
            type="button"
            onClick={async () => {
              setError(null);
              if (!query.trim()) return;
              setLoading(true);
              try {
                const retryData = await runSingleSearch(query.trim());
                setResults(retryData);
              } catch (err: unknown) {
                setError(err instanceof Error ? err.message : "Request failed");
              } finally {
                setLoading(false);
              }
            }}
            className="text-[11px] text-primary hover:underline"
          >
            Retry
          </button>
        </div>
      )}

      {hasResults && (
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] text-muted-foreground">Screening results</span>
          <button
            type="button"
            onClick={handleExport}
            className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1"
            aria-label="Export results as JSON"
          >
            <Download className="h-3 w-3" />
            Export JSON
          </button>
        </div>
      )}

      {results && (
        <div className="space-y-1.5">
          {results.screened_at && (
            <p className="text-[10px] text-muted-foreground">Screened at: {results.screened_at}</p>
          )}
          {results.matches.length === 0 && (
            <p className="text-[11px] text-muted-foreground">No matches found for "{results.query}".</p>
          )}
          {results.matches.slice(0, 10).map((m, i) => (
            <div key={`${m.entity_name}-${i}`} className="rounded border border-border bg-background/50 px-2.5 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold truncate">{m.entity_name}</span>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className={`px-1.5 py-0.5 rounded text-[11px] font-mono cursor-help ${MATCH_LEVEL_STYLES[m.match_level] ?? "bg-muted text-muted-foreground"}`}>
                      {m.match_level}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="left" className="max-w-[240px] text-xs">
                    {MATCH_LEVEL_LABELS[m.match_level] ?? m.match_level}
                  </TooltipContent>
                </Tooltip>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground mt-1 min-w-0">
                <span>Matched name</span>
                <span className="text-right truncate min-w-0">{m.matched_name}</span>
                <span>Score</span>
                <span className="text-right font-mono">{m.score}%</span>
                <span>Type</span>
                <span className="text-right">{m.entity_type || "-"}</span>
                <span>Program</span>
                <span className="text-right truncate">{m.program || "-"}</span>
                <span>Source</span>
                <span className="text-right">{m.source}</span>
              </div>
              {m.ownership_chain && m.ownership_chain.length > 0 && (
                <div className="mt-1 pt-1 border-t border-border/50">
                  <span className="text-[11px] text-muted-foreground font-mono">50%-Rule chain:</span>
                  {m.ownership_chain.map((c, j) => (
                    <p key={j} className="text-[11px] text-muted-foreground ml-2">
                      {c.entity} {"->"} {c.parent}
                      {c.ownership_pct != null && ` (${c.ownership_pct}%)`}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {batchResults && (
        <div className="space-y-2">
          {batchResults.results.map((r, idx) => (
            <div key={idx} className="rounded border border-border/60 px-2.5 py-1.5 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-mono text-foreground/80">{r.query}</span>
                {r.screened_at && <span className="text-[10px] text-muted-foreground">{r.screened_at}</span>}
              </div>
              {r.error && <p className="text-[11px] text-destructive">{r.error}</p>}
              {r.matches.length === 0 && !r.error && (
                <p className="text-[11px] text-muted-foreground">No matches.</p>
              )}
              {r.matches.slice(0, 5).map((m, i) => (
                <div key={i} className="flex items-center justify-between gap-2 text-[11px]">
                  <span className="truncate">{m.entity_name}</span>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className={`px-1 py-0.5 rounded font-mono cursor-help shrink-0 ${MATCH_LEVEL_STYLES[m.match_level] ?? "bg-muted"}`}>
                        {m.match_level}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="left" className="max-w-[240px] text-xs">
                      {MATCH_LEVEL_LABELS[m.match_level] ?? m.match_level}
                    </TooltipContent>
                  </Tooltip>
                </div>
              ))}
              {r.matches.length > 5 && (
                <p className="text-[10px] text-muted-foreground">+{r.matches.length - 5} more</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

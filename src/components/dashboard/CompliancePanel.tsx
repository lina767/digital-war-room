import { useState } from "react";
import { Shield, AlertTriangle, Search, ChevronDown, ChevronRight } from "lucide-react";
import { getApiBase } from "@/lib/api";
import type { ConflictData, GeofencingAlert } from "@/hooks/useConflictWebSocket";

const DISCLAIMER =
  "Intelligence signals only – not legal advice. Supports due diligence but does not replace legal review.";

const MATCH_LEVEL_STYLES: Record<string, string> = {
  EXACT: "bg-destructive text-destructive-foreground",
  STRONG_FUZZY: "bg-orange-500/90 text-black",
  WEAK_FUZZY: "bg-yellow-400/80 text-black",
  REVIEW: "bg-muted text-muted-foreground",
};

interface SanctionsResult {
  query: string;
  entity_name: string;
  matched_name: string;
  match_level: string;
  score: number;
  entity_type: string;
  program: string;
  source: string;
  ownership_chain?: Array<{ entity: string; parent: string; ownership_pct: number | null }>;
}

interface SanctionsResponse {
  query: string;
  matches: SanctionsResult[];
  disclaimer: string;
  threshold_policy: Record<string, unknown>;
}

function ZoneTypeBadge({ type }: { type: string }) {
  const cls =
    type === "sanctions"
      ? "bg-destructive/80 text-destructive-foreground"
      : type === "embargo"
        ? "bg-orange-500/80 text-black"
        : "bg-yellow-400/60 text-black";
  return (
    <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono uppercase ${cls}`}>
      {type}
    </span>
  );
}

function GeofencingAlerts({ alerts }: { alerts: GeofencingAlert[] }) {
  const [expanded, setExpanded] = useState(true);
  if (!alerts.length) return null;

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground w-full"
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <AlertTriangle className="h-3 w-3 text-orange-400" />
        <span>GEOFENCING ALERTS ({alerts.length})</span>
      </button>
      {expanded && (
        <div className="space-y-1.5 pl-4">
          {alerts.slice(0, 15).map((a, i) => (
            <div key={`${a.asset_id}-${a.zone_name}-${i}`} className="rounded border border-border bg-background/50 px-2.5 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold truncate">
                  {a.asset_name}
                </span>
                <ZoneTypeBadge type={a.zone_type} />
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground mt-1">
                <span>Zone</span>
                <span className="text-right font-mono">{a.zone_name.replace(/_/g, " ")}</span>
                <span>Type</span>
                <span className="text-right">{a.asset_type}</span>
                <span>Position</span>
                <span className="text-right font-mono">
                  {a.lat.toFixed(1)}° {a.lon.toFixed(1)}°
                </span>
                <span>Source</span>
                <span className="text-right">{a.source}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SanctionsSearch() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SanctionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const base = getApiBase();
      const resp = await fetch(`${base}/api/compliance/sanctions-check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), include_ownership_chains: true }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: SanctionsResponse = await resp.json();
      setResults(data);
    } catch (err: any) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-2">
      <form onSubmit={handleSearch} className="flex gap-1.5">
        <input
          type="text"
          placeholder="Firm or partner name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 rounded border border-border bg-background px-2 py-1 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="rounded border border-border bg-primary/10 px-2 py-1 text-xs font-mono hover:bg-primary/20 disabled:opacity-50 flex items-center gap-1"
        >
          <Search className="h-3 w-3" />
          {loading ? "…" : "Check"}
        </button>
      </form>

      {error && <p className="text-[10px] text-destructive">{error}</p>}

      {results && (
        <div className="space-y-1.5">
          {results.matches.length === 0 && (
            <p className="text-[11px] text-muted-foreground">
              No matches found for "{results.query}".
            </p>
          )}
          {results.matches.slice(0, 10).map((m, i) => (
            <div key={`${m.entity_name}-${i}`} className="rounded border border-border bg-background/50 px-2.5 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold truncate">{m.entity_name}</span>
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono ${MATCH_LEVEL_STYLES[m.match_level] ?? "bg-muted text-muted-foreground"}`}>
                  {m.match_level}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground mt-1">
                <span>Matched name</span>
                <span className="text-right truncate">{m.matched_name}</span>
                <span>Score</span>
                <span className="text-right font-mono">{m.score}%</span>
                <span>Type</span>
                <span className="text-right">{m.entity_type || "–"}</span>
                <span>Program</span>
                <span className="text-right truncate">{m.program || "–"}</span>
                <span>Source</span>
                <span className="text-right">{m.source}</span>
              </div>
              {m.ownership_chain && m.ownership_chain.length > 0 && (
                <div className="mt-1 pt-1 border-t border-border/50">
                  <span className="text-[9px] text-muted-foreground font-mono">50%-Rule chain:</span>
                  {m.ownership_chain.map((c, j) => (
                    <p key={j} className="text-[10px] text-muted-foreground ml-2">
                      {c.entity} → {c.parent}
                      {c.ownership_pct != null && ` (${c.ownership_pct}%)`}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface CompliancePanelProps {
  data: ConflictData | null;
}

export function CompliancePanel({ data }: CompliancePanelProps) {
  const compliance = data?.compliance;
  const alerts = compliance?.geofencing_alerts ?? [];

  return (
    <div className="rounded-lg border border-border bg-card/60 p-3 space-y-3">
      <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider flex items-center gap-1.5">
        <Shield className="h-3.5 w-3.5" />
        SANCTIONS COMPLIANCE
      </h3>

      <SanctionsSearch />

      <GeofencingAlerts alerts={alerts} />

      {alerts.length === 0 && (
        <p className="text-[10px] text-muted-foreground">
          No geofencing alerts in current SIGINT window.
        </p>
      )}

      <p className="text-[9px] text-muted-foreground border-t border-border/50 pt-2">
        {DISCLAIMER}
      </p>
    </div>
  );
}

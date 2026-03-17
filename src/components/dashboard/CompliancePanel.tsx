import { useRef, useState, useEffect } from "react";
import { Shield, AlertTriangle, Search, ChevronDown, ChevronRight, Radio, Info, Download, MessageCircle, MapPin, FileText } from "lucide-react";
import { IntelPanel } from "@/components/dashboard/IntelPanel";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { getApiBase } from "@/lib/api";
import { DASHBOARD_PANEL_TOOLTIPS } from "@/lib/dashboardPanelCopy";
import {
  COMPLIANCE_DISCLAIMER,
  COMPLIANCE_INTRO_FULL,
  COMPLIANCE_INTRO_SHORT,
  COMPLIANCE_NO_ALERTS_TEXT,
  DOC_QA_DISCLAIMER,
  DOC_QA_INTRO,
  DOC_QA_PLACEHOLDER,
  LISTS_COVERED_NOTE,
  MATCH_LEVEL_LABELS,
  RISK_LEVEL_LABELS,
} from "@/lib/complianceCopy";
import type { ConflictData, GeofencingAlert, AISAnomaly, ComplianceRiskScore } from "@/hooks/useConflictWebSocket";

const MATCH_LEVEL_STYLES: Record<string, string> = {
  EXACT: "bg-destructive text-destructive-foreground",
  STRONG_FUZZY: "bg-orange-500/90 text-black",
  WEAK_FUZZY: "bg-yellow-400/80 text-black",
  REVIEW: "bg-muted text-muted-foreground",
};

const RISK_LEVEL_STYLES: Record<string, string> = {
  CRITICAL: "bg-destructive text-destructive-foreground",
  HIGH: "bg-orange-500/90 text-black",
  MEDIUM: "bg-yellow-400/80 text-black",
  LOW: "bg-emerald-500/80 text-black",
};

/** Map risk driver factor to section id for drill-down scroll */
const DRIVER_SECTION_MAP: Record<string, string> = {
  CONFLICT_SANCTIONS_REGIME: "sanctions-lists",
  OFAC_SDN_EXTENSIVE: "sanctions-lists",
  OFAC_SDN_SIGNIFICANT: "sanctions-lists",
  OFAC_SDN_PRESENT: "sanctions-lists",
  EU_SANCTIONS_EXTENSIVE: "sanctions-lists",
  EU_SANCTIONS_PRESENT: "sanctions-lists",
  GEOFENCING_EMBARGO_ZONE: "geofencing-alerts",
  GEOFENCING_SANCTIONS_ZONE: "geofencing-alerts",
  AIS_SPOOFING: "ais-anomalies",
  AIS_DARK_ACTIVITY: "ais-anomalies",
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
  screened_at?: string;
}

interface SanctionsBatchResult {
  results: Array<{ query: string; matches: SanctionsResult[]; screened_at?: string; error?: string }>;
  threshold_policy: Record<string, unknown>;
  disclaimer: string;
}

function ZoneTypeBadge({ type }: { type: string }) {
  const cls =
    type === "sanctions"
      ? "bg-destructive/80 text-destructive-foreground"
      : type === "embargo"
        ? "bg-orange-500/80 text-black"
        : "bg-yellow-400/60 text-black";
  return (
    <span className={`px-1.5 py-0.5 rounded text-[11px] font-mono uppercase ${cls}`}>
      {type}
    </span>
  );
}

function CollapsibleSection({
  icon,
  label,
  count,
  defaultOpen = true,
  sectionId,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  defaultOpen?: boolean;
  sectionId?: string;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(defaultOpen);
  const contentId = sectionId ?? `collapse-${label.replace(/\s+/g, "-").toLowerCase()}`;
  if (count === 0) return null;

  return (
    <div className="space-y-1.5" id={sectionId}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls={contentId}
        className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground w-full"
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {icon}
        <span>{label} ({count})</span>
      </button>
      {expanded && <div id={contentId} className="space-y-1.5 pl-4" role="region">{children}</div>}
    </div>
  );
}

function RiskScoreDisplay({
  riskScore,
  onDriverClick,
}: {
  riskScore: ComplianceRiskScore;
  onDriverClick?: (sectionId: string) => void;
}) {
  const bandText = `${Math.round(riskScore.band.min * 100)}–${Math.round(riskScore.band.max * 100)}%`;
  const levelLabel = RISK_LEVEL_LABELS[riskScore.level];

  return (
    <div className="rounded-md border border-border/60 bg-background/50 px-3 py-2 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
          Compliance Risk
        </span>
        <span
          className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${RISK_LEVEL_STYLES[riskScore.level] ?? "bg-muted text-muted-foreground"}`}
          title={levelLabel}
        >
          {riskScore.level}
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg font-bold text-primary">{riskScore.numeric_score}</span>
        <span className="text-[11px] text-muted-foreground">/100 · Band: {bandText} (rough range)</span>
      </div>
      {riskScore.drivers.length > 0 && (
        <ul className="space-y-1">
          {riskScore.drivers.slice(0, 6).map((d, i) => {
            const sectionId = DRIVER_SECTION_MAP[d.factor];
            const isClickable = sectionId && onDriverClick;
            return (
              <li key={i} className="text-[11px] text-muted-foreground">
                <div className="flex gap-1.5">
                  <span className="mt-[3px] h-1 w-1 rounded-full bg-primary/80 flex-shrink-0" />
                  <div className="min-w-0">
                    {isClickable ? (
                      <button
                        type="button"
                        onClick={() => onDriverClick(sectionId)}
                        className="text-left hover:text-foreground focus:outline-none focus:ring-1 focus:ring-primary rounded"
                      >
                        <span className="font-mono text-foreground/80">{d.factor}</span>: {d.detail}
                      </button>
                    ) : (
                      <>
                        <span className="font-mono text-foreground/80">{d.factor}</span>: {d.detail}
                      </>
                    )}
                    {d.programs && (
                      <span className="ml-1 text-[11px] text-muted-foreground/70">
                        [{d.programs}]
                      </span>
                    )}
                    {d.note && (
                      <p className="text-[11px] text-muted-foreground/60 mt-0.5 leading-tight">
                        {d.note}
                      </p>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function AISAnomaliesSection({ anomalies }: { anomalies: AISAnomaly[] }) {
  return (
    <CollapsibleSection
      icon={<Radio className="h-3 w-3 text-red-400" />}
      label="AIS ANOMALIES"
      count={anomalies.length}
      defaultOpen={true}
      sectionId="ais-anomalies"
    >
      {anomalies.slice(0, 10).map((a, i) => (
        <div key={`${a.asset_id}-${a.anomaly_type}-${i}`} className="rounded border border-border bg-background/50 px-2.5 py-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold truncate">{a.asset_name}</span>
            <div className="flex items-center gap-1">
              <span className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${a.anomaly_type === "spoofing" ? "bg-red-500/80 text-white" : "bg-purple-500/80 text-white"}`}>
                {a.anomaly_type === "spoofing" ? "SPOOF" : "DARK"}
              </span>
              <span className={`px-1.5 py-0.5 rounded text-[11px] font-mono ${a.severity === "HIGH" ? "bg-orange-500/80 text-black" : "bg-yellow-400/60 text-black"}`}>
                {a.severity}
              </span>
              {a.confidence && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted/80 text-muted-foreground cursor-help">
                      {a.confidence}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="left" className="max-w-[200px] text-xs">
                    Heuristic confidence: {a.confidence === "HIGH" ? "strong indicator" : "moderate indicator"}.
                  </TooltipContent>
                </Tooltip>
              )}
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground mt-1 leading-snug">{a.detail}</p>
          {a.zone_name && (
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Zone: <span className="font-mono">{a.zone_name.replace(/_/g, " ")}</span>
            </p>
          )}
          {(a.gap_hours != null || a.last_seen_at != null) && (
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[10px] text-muted-foreground">
              {a.gap_hours != null && (
                <span>Gap: <span className="font-mono">{a.gap_hours}h</span></span>
              )}
              {a.last_seen_at != null && (
                <span>Last seen: <span className="font-mono">{new Date(a.last_seen_at * 1000).toISOString().replace("T", " ").slice(0, 19)}Z</span></span>
              )}
            </div>
          )}
        </div>
      ))}
    </CollapsibleSection>
  );
}

function GeofencingAlerts({ alerts }: { alerts: GeofencingAlert[] }) {
  return (
    <CollapsibleSection
      icon={<AlertTriangle className="h-3 w-3 text-orange-400" />}
      label="GEOFENCING ALERTS"
      count={alerts.length}
      defaultOpen={true}
      sectionId="geofencing-alerts"
    >
      {alerts.slice(0, 15).map((a, i) => (
        <div key={`${a.asset_id}-${a.zone_name}-${i}`} className="rounded border border-border bg-background/50 px-2.5 py-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold truncate">{a.asset_name}</span>
            <ZoneTypeBadge type={a.zone_type} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground mt-1 min-w-0">
            <span>Zone</span>
            <span className="text-right font-mono truncate">{a.zone_name.replace(/_/g, " ")}</span>
            <span>Type</span>
            <span className="text-right">{a.asset_type}</span>
            <span>Position</span>
            <span className="text-right font-mono">
              {a.lat.toFixed(1)}° {a.lon.toFixed(1)}°
            </span>
            <span>Source</span>
            <span className="text-right">{a.source}</span>
            {a.first_seen_at != null && (
              <>
                <span>First seen</span>
                <span className="text-right font-mono text-[10px]">
                  {new Date(a.first_seen_at * 1000).toISOString().replace("T", " ").slice(0, 19)}Z
                </span>
              </>
            )}
            {a.last_seen_at != null && (
              <>
                <span>Last seen</span>
                <span className="text-right font-mono text-[10px]">
                  {new Date(a.last_seen_at * 1000).toISOString().replace("T", " ").slice(0, 19)}Z
                </span>
              </>
            )}
            {a.duration_hours != null && a.duration_hours >= 0 && (
              <>
                <span>Duration</span>
                <span className="text-right font-mono">{a.duration_hours}h</span>
              </>
            )}
          </div>
        </div>
      ))}
    </CollapsibleSection>
  );
}

interface RouteScreeningWaypoint {
  label: string;
  lat: number;
  lon: number;
  country_code?: string;
  port_type?: string;
}

interface RouteScreeningResult {
  route_label: string;
  waypoints: Array<{ label: string; lat: number; lon: number }>;
  zone_hits: Array<{ waypoint: string; zone_name: string; zone_type: string; zone_source?: string }>;
  suspicious_hops: Array<{ waypoint: string; country_code: string; hub_label: string; condition: string; rationale?: string }>;
  touches_sanctions_zone: boolean;
  disclaimer?: string;
}

function RouteScreeningSection() {
  const [routeLabel, setRouteLabel] = useState("");
  const [waypointsText, setWaypointsText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RouteScreeningResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!routeLabel.trim()) return;
    const lines = waypointsText.trim().split(/\n/).filter(Boolean);
    const waypoints: RouteScreeningWaypoint[] = lines.slice(0, 20).map((line) => {
      const parts = line.split(/[\t,;]+/).map((p) => p.trim());
      const label = parts[0] || "";
      const lat = parseFloat(parts[1] ?? "0");
      const lon = parseFloat(parts[2] ?? "0");
      const country_code = parts[3] ?? "";
      const port_type = parts[4] ?? "port";
      return { label, lat, lon, country_code, port_type };
    }).filter((wp) => !Number.isNaN(wp.lat) && !Number.isNaN(wp.lon));
    if (waypoints.length === 0) {
      setError("Add at least one waypoint (label, lat, lon per line).");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/api/compliance/route-screening`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ route_label: routeLabel.trim(), waypoints }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as RouteScreeningResult;
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <CollapsibleSection
      icon={<MapPin className="h-3 w-3 text-primary" />}
      label="ROUTE SCREENING"
      count={1}
      defaultOpen={false}
      sectionId="route-screening"
    >
      <form onSubmit={handleSubmit} className="space-y-2">
        <input
          type="text"
          placeholder="Route name (e.g. Bandar Abbas → Rotterdam)"
          value={routeLabel}
          onChange={(e) => setRouteLabel(e.target.value)}
          className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
        />
        <textarea
          placeholder="One waypoint per line: label, lat, lon [, country_code, port_type]"
          value={waypointsText}
          onChange={(e) => setWaypointsText(e.target.value)}
          rows={3}
          className="w-full rounded border border-border bg-background px-2 py-1 text-[11px] font-mono resize-y"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded border border-border bg-primary/10 px-2 py-1 text-[11px] font-mono hover:bg-primary/20 disabled:opacity-50"
        >
          {loading ? "Screening…" : "Screen route"}
        </button>
      </form>
      {error && <p className="text-[11px] text-destructive">{error}</p>}
      {result && (
        <div className="space-y-1.5 mt-2">
          {result.touches_sanctions_zone && (
            <p className="text-[11px] font-semibold text-destructive">Route touches sanctions zone.</p>
          )}
          {result.zone_hits.length > 0 && (
            <div>
              <span className="text-[11px] text-muted-foreground">Zone hits:</span>
              {result.zone_hits.map((h, i) => (
                <p key={i} className="text-[11px] pl-2">
                  {h.waypoint} → <span className="font-mono">{h.zone_name}</span> ({h.zone_type})
                </p>
              ))}
            </div>
          )}
          {result.suspicious_hops.length > 0 && (
            <div>
              <span className="text-[11px] text-muted-foreground">Suspicious hops:</span>
              {result.suspicious_hops.map((h, i) => (
                <p key={i} className="text-[11px] pl-2">
                  {h.waypoint} ({h.country_code}): {h.hub_label} – {h.condition}
                </p>
              ))}
            </div>
          )}
          {!result.touches_sanctions_zone && result.zone_hits.length === 0 && result.suspicious_hops.length === 0 && (
            <p className="text-[11px] text-muted-foreground">No zone hits or intermediary flags.</p>
          )}
        </div>
      )}
    </CollapsibleSection>
  );
}

interface ZonesResponse {
  sanctions_zones: Array<{ name?: string; zone_type?: string; source?: string }>;
  all_zones: Array<{ name?: string; zone_type?: string; source?: string }>;
}

function ComplianceZonesSection() {
  const [zones, setZones] = useState<ZonesResponse | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${getApiBase()}/api/compliance/zones`)
      .then((res) => res.ok ? res.json() : null)
      .then((data: ZonesResponse | null) => {
        if (!cancelled && data) setZones(data);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const count = zones ? zones.sanctions_zones.length + zones.all_zones.length : 0;
  if (count === 0) return null;

  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground hover:text-foreground w-full"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <MapPin className="h-3 w-3" />
        <span>Zones ({count})</span>
      </button>
      {open && zones && (
        <div className="pl-4 space-y-1 text-[11px]">
          <div>
            <span className="text-muted-foreground">Sanctions:</span>
            {zones.sanctions_zones.map((z, i) => (
              <p key={i} className="font-mono truncate">{z.name ?? "—"}</p>
            ))}
          </div>
          <div>
            <span className="text-muted-foreground">All zones:</span>
            {zones.all_zones.slice(0, 15).map((z, i) => (
              <p key={i} className="font-mono truncate">{z.name ?? "—"}</p>
            ))}
            {zones.all_zones.length > 15 && (
              <p className="text-muted-foreground">+{zones.all_zones.length - 15} more</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function SanctionsSearch({ data }: { data: ConflictData | null }) {
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
      const data = await runSingleSearch(query.trim(), signal);
      setResults(data);
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
      const data: SanctionsBatchResult = await resp.json();
      setBatchResults(data);
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
          placeholder="Firm or partner name…"
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
          {loading ? "…" : "Check"}
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
                const data = await runSingleSearch(query.trim());
                setResults(data);
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
            <p className="text-[11px] text-muted-foreground">
              No matches found for "{results.query}".
            </p>
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
                <span className="text-right">{m.entity_type || "–"}</span>
                <span>Program</span>
                <span className="text-right truncate">{m.program || "–"}</span>
                <span>Source</span>
                <span className="text-right">{m.source}</span>
              </div>
              {m.ownership_chain && m.ownership_chain.length > 0 && (
                <div className="mt-1 pt-1 border-t border-border/50">
                  <span className="text-[11px] text-muted-foreground font-mono">50%-Rule chain:</span>
                  {m.ownership_chain.map((c, j) => (
                    <p key={j} className="text-[11px] text-muted-foreground ml-2">
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

interface DocumentQAResponse {
  answer: string;
  confidence?: number;
  sources?: string[];
  disclaimer?: string;
}

function DocumentManagementSection() {
  const [ingestUrl, setIngestUrl] = useState("");
  const [ingestConflict, setIngestConflict] = useState("Iran");
  const [ingestLoading, setIngestLoading] = useState(false);
  const [docList, setDocList] = useState<Array<{ id?: string; url?: string; source?: string; conflict?: string }>>([]);
  const [listLoading, setListLoading] = useState(false);
  const [qaQuestion, setQaQuestion] = useState("");
  const [qaLoading, setQaLoading] = useState(false);
  const [qaResult, setQaResult] = useState<{ answer?: string; confidence?: number; sources?: string[] } | null>(null);

  async function handleIngest(e: React.FormEvent) {
    e.preventDefault();
    if (!ingestUrl.trim()) return;
    setIngestLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/api/documents/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: ingestUrl.trim(), source: "pdf", conflict: ingestConflict.trim() }),
      });
      if (res.ok) {
        setIngestUrl("");
        const listRes = await fetch(`${getApiBase()}/api/documents`);
        if (listRes.ok) {
          const arr = await listRes.json();
          setDocList(Array.isArray(arr) ? arr : arr?.documents ?? []);
        }
      }
    } finally {
      setIngestLoading(false);
    }
  }

  async function handleList() {
    setListLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/api/documents`);
      if (res.ok) {
        const arr = await res.json();
        setDocList(Array.isArray(arr) ? arr : arr?.documents ?? []);
      }
    } finally {
      setListLoading(false);
    }
  }

  async function handleDocQa(e: React.FormEvent) {
    e.preventDefault();
    if (!qaQuestion.trim()) return;
    setQaLoading(true);
    setQaResult(null);
    try {
      const res = await fetch(`${getApiBase()}/api/documents/qa`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: qaQuestion.trim(), conflict: "Iran" }),
      });
      if (res.ok) {
        const data = await res.json();
        setQaResult(data);
      }
    } finally {
      setQaLoading(false);
    }
  }

  return (
    <CollapsibleSection icon={<FileText className="h-3 w-3 text-primary" />} label="DOCUMENT MANAGEMENT" count={1} defaultOpen={false}>
      <form onSubmit={handleIngest} className="space-y-1.5">
        <input
          type="url"
          placeholder="PDF URL to ingest"
          value={ingestUrl}
          onChange={(e) => setIngestUrl(e.target.value)}
          className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
        />
        <input
          type="text"
          placeholder="Conflict (optional)"
          value={ingestConflict}
          onChange={(e) => setIngestConflict(e.target.value)}
          className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
        />
        <div className="flex gap-2">
          <button type="submit" disabled={ingestLoading} className="rounded border border-border bg-primary/10 px-2 py-1 text-[11px]">
            {ingestLoading ? "Ingesting…" : "Ingest"}
          </button>
          <button type="button" onClick={handleList} disabled={listLoading} className="rounded border border-border px-2 py-1 text-[11px]">
            {listLoading ? "…" : "List docs"}
          </button>
        </div>
      </form>
      {docList.length > 0 && (
        <div className="text-[11px] text-muted-foreground">
          {docList.length} document(s): {docList.map((d) => d.id ?? d.url ?? "?").slice(0, 3).join(", ")}
          {docList.length > 3 ? "…" : ""}
        </div>
      )}
      <form onSubmit={handleDocQa} className="space-y-1.5 mt-2 pt-2 border-t border-border/50">
        <input
          type="text"
          placeholder="Question over ingested docs"
          value={qaQuestion}
          onChange={(e) => setQaQuestion(e.target.value)}
          className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
        />
        <button type="submit" disabled={qaLoading} className="rounded border border-border bg-primary/10 px-2 py-1 text-[11px]">
          {qaLoading ? "…" : "QA"}
        </button>
      </form>
      {qaResult && (
        <div className="mt-1.5 rounded border border-border bg-background/50 px-2 py-1.5 text-[11px]">
          <p>{qaResult.answer ?? "—"}</p>
          {qaResult.confidence != null && <p className="text-muted-foreground">Confidence: {qaResult.confidence}</p>}
        </div>
      )}
    </CollapsibleSection>
  );
}

function DocumentQASection({ data }: { data: ConflictData | null }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DocumentQAResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  function buildContext() {
    const c = data?.compliance;
    if (!c) return undefined;
    const sample = c.ofac_sdn?.sample ?? [];
    const ofacSample: string[] = sample.map((s: { name?: string; type?: string; program?: string }) => {
      const name = s.name?.trim();
      if (!name) return "";
      const type = s.type;
      const program = s.program;
      if (type || program) return `${name} (${[type, program].filter(Boolean).join(", ")})`;
      return name;
    }).filter(Boolean);
    const programs = c.ofac_sdn?.programs ?? [];
    const ofacProgramsSummary = programs.length > 0
      ? programs.slice(0, 12).map((p: { name?: string; count?: number }) => `${p.name ?? "?"} (${p.count ?? 0})`).join(", ")
      : undefined;
    const riskLevel = c.risk_score?.level;
    const drivers = c.risk_score?.drivers ?? [];
    const riskDriversSummary = drivers.length > 0
      ? drivers.slice(0, 6).map((d) => `${d.factor}: ${d.detail}`).join("; ")
      : undefined;
    return {
      ofac_sample: ofacSample.length > 0 ? ofacSample : undefined,
      ofac_programs_summary: ofacProgramsSummary,
      risk_level: riskLevel ?? undefined,
      risk_drivers_summary: riskDriversSummary,
    };
  }

  async function handleAsk() {
    if (!question.trim()) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const base = getApiBase();
      const resp = await fetch(`${base}/api/compliance/document-qa`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          conflict: data?.conflict ?? "Iran",
          context: buildContext(),
        }),
        signal: abortRef.current.signal,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json: DocumentQAResponse = await resp.json();
      setResult(json);
    } catch (err: unknown) {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-2">
      <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
        <MessageCircle className="h-3 w-3" />
        Ask about sanctions documents
      </span>
      <p className="text-[11px] text-muted-foreground">{DOC_QA_INTRO}</p>
      <div className="flex flex-col gap-1.5">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={DOC_QA_PLACEHOLDER}
          rows={2}
          aria-label="Question about current compliance context"
          className="w-full rounded border border-border bg-background px-2 py-1.5 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary resize-y min-h-[48px]"
        />
        <button
          type="button"
          onClick={handleAsk}
          disabled={loading || !question.trim()}
          aria-label="Ask question about compliance context"
          className="self-start rounded border border-border bg-primary/10 px-2 py-1 text-xs font-mono hover:bg-primary/20 disabled:opacity-50"
        >
          {loading ? "…" : "Ask"}
        </button>
      </div>
      {error && (
        <div className="flex items-center gap-2">
          <p className="text-[11px] text-destructive">{error}</p>
          <button
            type="button"
            onClick={handleAsk}
            className="text-[11px] text-primary hover:underline"
          >
            Retry
          </button>
        </div>
      )}
      {result && (
        <div className="rounded border border-border bg-background/50 px-2.5 py-1.5 space-y-1">
          <p className="text-[11px] text-foreground whitespace-pre-wrap">{result.answer}</p>
          {result.confidence != null && result.confidence > 0 && (
            <p className="text-[10px] text-muted-foreground">
              Confidence: {Math.round(result.confidence * 100)}%
            </p>
          )}
          <p className="text-[10px] text-muted-foreground/80 border-t border-border/50 pt-1">
            {result.disclaimer ?? DOC_QA_DISCLAIMER}
          </p>
        </div>
      )}
    </div>
  );
}

interface CompliancePanelProps {
  data: ConflictData | null;
}

function OFACEUSummary({ compliance }: { compliance: NonNullable<ConflictData["compliance"]> }) {
  const ofacTotal = compliance.ofac_sdn?.total_matches ?? 0;
  const euMentions = compliance.eu_sanctions?.keyword_mentions ?? 0;
  const ofacPrograms = compliance.ofac_sdn?.programs ?? [];
  const ofacError = compliance.ofac_sdn?.error;
  const euError = compliance.eu_sanctions?.error;

  if (ofacTotal === 0 && euMentions === 0 && !ofacError && !euError) return null;

  const sample = compliance.ofac_sdn?.sample ?? [];

  return (
    <div id="sanctions-lists" className="rounded-md border border-border/60 bg-background/50 px-3 py-2 space-y-1">
      <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
        Sanctions Lists (DIPLO Agent)
      </span>
      <div className="space-y-0.5">
        {ofacTotal > 0 && (
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[11px] text-muted-foreground">OFAC SDN entries</span>
            <span className="font-mono text-xs font-semibold text-foreground">{ofacTotal}</span>
          </div>
        )}
        {ofacError && ofacTotal === 0 && (
          <p className="text-[11px] text-orange-400">OFAC SDN fetch failed (large CSV download). Regime-level scoring still active.</p>
        )}
        {euMentions > 0 && (
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[11px] text-muted-foreground">EU sanctions mentions</span>
            <span className="font-mono text-xs font-semibold text-foreground">{euMentions}</span>
          </div>
        )}
        {euError && euMentions === 0 && (
          <p className="text-[11px] text-orange-400">EU sanctions fetch failed.</p>
        )}
      </div>
      {ofacPrograms.length > 0 && (
        <div className="mt-0.5">
          <span className="text-[11px] text-muted-foreground">Programs: </span>
          <span className="text-[11px] text-muted-foreground/80">
            {ofacPrograms.slice(0, 6).map(p => `${p.name} (${p.count})`).join(", ")}
          </span>
        </div>
      )}
      {sample.length > 0 && (
        <p className="text-[11px] text-muted-foreground leading-snug">
          Sample: {sample.slice(0, 3).map(s => s.name).filter(Boolean).join(" · ")}
        </p>
      )}
      <p className="text-[10px] text-muted-foreground/80 pt-0.5">{LISTS_COVERED_NOTE}</p>
    </div>
  );
}

export function CompliancePanel({ data }: CompliancePanelProps) {
  const compliance = data?.compliance;
  const alerts = compliance?.geofencing_alerts ?? [];
  const anomalies = compliance?.ais_anomalies ?? [];
  const riskScore = compliance?.risk_score;
  const sigintSummary = compliance?.sigint_window_summary;

  const hasRealtimeSignals = alerts.length > 0 || anomalies.length > 0;

  const scrollToSection = (sectionId: string) => {
    document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <IntelPanel
      title="SANCTIONS COMPLIANCE"
      icon={<Shield className="h-3.5 w-3.5 text-muted-foreground" />}
      tooltipContent={DASHBOARD_PANEL_TOOLTIPS["SANCTIONS COMPLIANCE"]}
    >
      <TooltipProvider>
        <p className="text-[11px] text-muted-foreground flex items-start gap-1.5">
          <span>{COMPLIANCE_INTRO_SHORT}</span>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="shrink-0 cursor-help text-muted-foreground/80 hover:text-foreground" aria-label="More information">
                <Info className="h-3.5 w-3.5" />
              </span>
            </TooltipTrigger>
            <TooltipContent side="right" className="max-w-[320px] text-xs">
              {COMPLIANCE_INTRO_FULL}
            </TooltipContent>
          </Tooltip>
        </p>

        {riskScore && (
          <ErrorBoundary sectionLabel="Compliance Risk">
            <RiskScoreDisplay riskScore={riskScore} onDriverClick={scrollToSection} />
          </ErrorBoundary>
        )}

        {compliance && (
          <ErrorBoundary sectionLabel="Sanctions Lists">
            <OFACEUSummary compliance={compliance} />
          </ErrorBoundary>
        )}

        <ErrorBoundary sectionLabel="Sanctions Search">
          <SanctionsSearch data={data} />
        </ErrorBoundary>

        <ErrorBoundary sectionLabel="Route Screening">
          <RouteScreeningSection />
        </ErrorBoundary>

        <ErrorBoundary sectionLabel="Zones">
          <ComplianceZonesSection />
        </ErrorBoundary>

        <ErrorBoundary sectionLabel="Document QA">
          <DocumentQASection data={data} />
        </ErrorBoundary>

        <ErrorBoundary sectionLabel="Document Management">
          <DocumentManagementSection />
        </ErrorBoundary>

        <div id="geofencing-alerts">
          <ErrorBoundary sectionLabel="Geofencing Alerts">
            <GeofencingAlerts alerts={alerts} />
          </ErrorBoundary>
        </div>

        <div id="ais-anomalies">
          <ErrorBoundary sectionLabel="AIS Anomalies">
            <AISAnomaliesSection anomalies={anomalies} />
          </ErrorBoundary>
        </div>

        {!hasRealtimeSignals && (
          <div className="space-y-0.5">
            <p className="text-[11px] text-muted-foreground">{COMPLIANCE_NO_ALERTS_TEXT}</p>
            {sigintSummary != null && (
              <p className="text-[11px] text-muted-foreground/90">
                This run: {sigintSummary.aircraft_count} aircraft, {sigintSummary.ships_count} ships in conflict region; none in sanctions zones.
              </p>
            )}
          </div>
        )}

        <p className="text-[11px] text-muted-foreground border-t border-border/50 pt-2">
          {compliance?.disclaimer ?? COMPLIANCE_DISCLAIMER}
        </p>
      </TooltipProvider>
    </IntelPanel>
  );
}

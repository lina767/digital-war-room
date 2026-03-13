import { useState } from "react";
import { Shield, AlertTriangle, Search, ChevronDown, ChevronRight, Radio, Eye, ExternalLink } from "lucide-react";
import { getApiBase } from "@/lib/api";
import type { ConflictData, GeofencingAlert, AISAnomaly, ComplianceRiskScore } from "@/hooks/useConflictWebSocket";

const DISCLAIMER =
  "Intelligence signals only – not legal advice. Supports due diligence but does not replace legal review.";


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

function CollapsibleSection({
  icon,
  label,
  count,
  defaultOpen = true,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(defaultOpen);
  if (count === 0) return null;

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground hover:text-foreground w-full"
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {icon}
        <span>{label} ({count})</span>
      </button>
      {expanded && <div className="space-y-1.5 pl-4">{children}</div>}
    </div>
  );
}

function RiskScoreDisplay({ riskScore }: { riskScore: ComplianceRiskScore }) {
  const bandText = `${Math.round(riskScore.band.min * 100)}–${Math.round(riskScore.band.max * 100)}%`;

  return (
    <div className="rounded-md border border-border/60 bg-background/50 px-3 py-2 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
          Compliance Risk
        </span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${RISK_LEVEL_STYLES[riskScore.level] ?? "bg-muted text-muted-foreground"}`}>
          {riskScore.level}
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg font-bold text-primary">{riskScore.numeric_score}</span>
        <span className="text-[10px] text-muted-foreground">/100 · Band: {bandText}</span>
      </div>
      {riskScore.drivers.length > 0 && (
        <ul className="space-y-1">
          {riskScore.drivers.slice(0, 6).map((d, i) => (
            <li key={i} className="text-[10px] text-muted-foreground">
              <div className="flex gap-1.5">
                <span className="mt-[3px] h-1 w-1 rounded-full bg-primary/80 flex-shrink-0" />
                <div>
                  <span className="font-mono text-foreground/80">{d.factor}</span>: {d.detail}
                  {(d as any).programs && (
                    <span className="ml-1 text-[9px] text-muted-foreground/70">
                      [{(d as any).programs}]
                    </span>
                  )}
                  {(d as any).note && (
                    <p className="text-[9px] text-muted-foreground/60 mt-0.5 leading-tight">
                      {(d as any).note}
                    </p>
                  )}
                </div>
              </div>
            </li>
          ))}
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
    >
      {anomalies.slice(0, 10).map((a, i) => (
        <div key={`${a.asset_id}-${a.anomaly_type}-${i}`} className="rounded border border-border bg-background/50 px-2.5 py-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold truncate">{a.asset_name}</span>
            <div className="flex items-center gap-1">
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono ${a.anomaly_type === "spoofing" ? "bg-red-500/80 text-white" : "bg-purple-500/80 text-white"}`}>
                {a.anomaly_type === "spoofing" ? "SPOOF" : "DARK"}
              </span>
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono ${a.severity === "HIGH" ? "bg-orange-500/80 text-black" : "bg-yellow-400/60 text-black"}`}>
                {a.severity}
              </span>
            </div>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1 leading-snug">{a.detail}</p>
          {a.zone_name && (
            <p className="text-[9px] text-muted-foreground mt-0.5">
              Zone: <span className="font-mono">{a.zone_name.replace(/_/g, " ")}</span>
            </p>
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
    >
      {alerts.slice(0, 15).map((a, i) => (
        <div key={`${a.asset_id}-${a.zone_name}-${i}`} className="rounded border border-border bg-background/50 px-2.5 py-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold truncate">{a.asset_name}</span>
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
    </CollapsibleSection>
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

function OFACEUSummary({ compliance }: { compliance: NonNullable<ConflictData["compliance"]> }) {
  const ofacTotal = compliance.ofac_sdn?.total_matches ?? 0;
  const euMentions = compliance.eu_sanctions?.keyword_mentions ?? 0;
  const ofacPrograms = compliance.ofac_sdn?.programs ?? [];
  const ofacError = compliance.ofac_sdn?.error;
  const euError = compliance.eu_sanctions?.error;

  if (ofacTotal === 0 && euMentions === 0 && !ofacError && !euError) return null;

  return (
    <div className="rounded-md border border-border/60 bg-background/50 px-3 py-2 space-y-1">
      <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
        Sanctions Lists (DIPLO Agent)
      </span>
      <div className="space-y-0.5">
        {ofacTotal > 0 && (
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[10px] text-muted-foreground">OFAC SDN entries</span>
            <span className="font-mono text-xs font-semibold text-foreground">{ofacTotal}</span>
          </div>
        )}
        {ofacError && ofacTotal === 0 && (
          <p className="text-[9px] text-orange-400">OFAC SDN fetch failed (large CSV download). Regime-level scoring still active.</p>
        )}
        {euMentions > 0 && (
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[10px] text-muted-foreground">EU sanctions mentions</span>
            <span className="font-mono text-xs font-semibold text-foreground">{euMentions}</span>
          </div>
        )}
        {euError && euMentions === 0 && (
          <p className="text-[9px] text-orange-400">EU sanctions fetch failed.</p>
        )}
      </div>
      {ofacPrograms.length > 0 && (
        <div className="mt-0.5">
          <span className="text-[9px] text-muted-foreground">Programs: </span>
          <span className="text-[9px] text-muted-foreground/80">
            {ofacPrograms.slice(0, 6).map(p => `${p.name} (${p.count})`).join(", ")}
          </span>
        </div>
      )}
      {(compliance.ofac_sdn?.sample?.length ?? 0) > 0 && (
        <p className="text-[9px] text-muted-foreground leading-snug">
          Sample: {compliance.ofac_sdn!.sample!.slice(0, 3).map(s => s.name).filter(Boolean).join(" · ")}
        </p>
      )}
    </div>
  );
}

export function CompliancePanel({ data }: CompliancePanelProps) {
  const compliance = data?.compliance;
  const alerts = compliance?.geofencing_alerts ?? [];
  const anomalies = compliance?.ais_anomalies ?? [];
  const riskScore = compliance?.risk_score;

  const hasRealtimeSignals = alerts.length > 0 || anomalies.length > 0;

  return (
    <div className="rounded-lg border border-border bg-card/60 p-3 space-y-3">
      <h3 className="font-mono text-[10px] text-muted-foreground tracking-wider flex items-center gap-1.5">
        <Shield className="h-3.5 w-3.5" />
        SANCTIONS COMPLIANCE
      </h3>

      {riskScore && <RiskScoreDisplay riskScore={riskScore} />}

      {compliance && <OFACEUSummary compliance={compliance} />}

      <SanctionsSearch />

      <GeofencingAlerts alerts={alerts} />

      <AISAnomaliesSection anomalies={anomalies} />

      {!hasRealtimeSignals && (
        <p className="text-[10px] text-muted-foreground">
          No geofencing or AIS anomaly alerts in current SIGINT window.
        </p>
      )}

      {(compliance?.ofac_recent_actions?.length ?? 0) > 0 && (
        <div className="border-t border-border/50 pt-2 space-y-1.5">
          <span className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
            Recent OFAC / Treasury Actions
          </span>
          {compliance!.ofac_recent_actions!.slice(0, 3).map((action, i) => (
            <a
              key={i}
              href={action.url ?? "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-1.5 text-[10px] text-muted-foreground hover:text-foreground group"
            >
              <ExternalLink className="h-3 w-3 mt-0.5 flex-shrink-0 group-hover:text-primary" />
              <span>
                <span className="font-semibold">{action.title}</span>
                {action.published && (
                  <span className="text-[9px] text-muted-foreground/60 ml-1">({action.published})</span>
                )}
                {action.summary && (
                  <>
                    <br />
                    <span className="text-[9px]">{action.summary}</span>
                  </>
                )}
              </span>
            </a>
          ))}
        </div>
      )}

      <p className="text-[9px] text-muted-foreground border-t border-border/50 pt-2">
        {DISCLAIMER}
      </p>
    </div>
  );
}

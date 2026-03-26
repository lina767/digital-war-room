import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Loader2 } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { FindingConfidenceBadge, normalizeFindingConfidence } from "@/components/dashboard/FindingConfidenceBadge";
import { apiUrl } from "@/lib/api";
import type { AnalyzeResponse } from "@/lib/api";

type ConfidenceText = "high" | "medium" | "low" | string;

type VerifiedOutcome = {
  outcome?: string;
  verification_status?: string;
  confidence?: ConfidenceText;
  as_of?: string;
  sources?: string[];
};

type ConfidenceBadgeItem = {
  label?: string;
  status?: string;
  confidence?: ConfidenceText;
  detail?: string;
};

type PrecomputedAgentResult = {
  agent?: string;
  score?: number;
  confidence?: ConfidenceText;
  contribution?: string;
};

type DemoPayload = AnalyzeResponse & {
  _demo?: boolean;
  scenario_id?: string;
  scenario_title?: string;
  scenario_note?: string;
  verified_outcomes?: VerifiedOutcome[];
  cross_validation?: AnalyzeResponse["cross_validation"] & {
    pipeline_version?: string;
    overall_confidence?: ConfidenceText;
    consensus_score?: number;
    checks_passed?: number;
    checks_total?: number;
    confidence_badges?: ConfidenceBadgeItem[];
  };
  precomputed_agent_results?: PrecomputedAgentResult[];
};

const THREAT_BADGE: Record<string, string> = {
  LOW: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  ELEVATED: "bg-warning/20 text-warning border-warning/30",
  HIGH: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  CRITICAL: "bg-destructive/20 text-destructive border-destructive/30",
};

function threatClass(level: string | null | undefined): string {
  return THREAT_BADGE[level ?? "HIGH"] ?? THREAT_BADGE.HIGH;
}

const CHECK_BADGE: Record<string, string> = {
  pass: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  watch: "bg-amber-500/15 text-amber-200 border-amber-500/35",
  fail: "bg-destructive/20 text-destructive border-destructive/40",
};

export default function DemoPage() {
  const [data, setData] = useState<DemoPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(apiUrl("/api/demo/snapshot"), { credentials: "same-origin" });
        if (!res.ok) {
          throw new Error(res.status === 503 ? "Demo snapshot unavailable." : `HTTP ${res.status}`);
        }
        const json = (await res.json()) as DemoPayload;
        if (!cancelled) setData(json);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load demo");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <SEO
        title="Historical demo snapshot – Digital War Room"
        description="Explore a historical analysis run with real data-quality scoring, BLUF narrative, and multi-stream context."
        path="/demo"
        imageAlt="Digital War Room historical snapshot"
      />
      <div className="min-h-screen bg-background text-foreground">
        <header className="border-b border-border">
          <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6">
            <a href="/" className="font-mono text-xs font-semibold tracking-[0.2em] text-muted-foreground hover:text-primary">
              DIGITAL WAR ROOM
            </a>
            <nav className="flex flex-wrap items-center gap-3 text-sm">
              <a href="/" className="text-muted-foreground hover:text-foreground">
                Home
              </a>
              <Link to="/app/dashboard" className="text-muted-foreground hover:text-foreground">
                Live dashboard
              </Link>
            </nav>
          </div>
        </header>

        <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
          <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">Historical snapshot</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
            {data?.scenario_title ?? "Historical analysis run"}
          </h1>
          {data?.scenario_note && (
            <p className="mt-3 text-sm text-muted-foreground">{data.scenario_note}</p>
          )}

          {loading && (
            <div className="mt-12 flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
              Loading historical run…
            </div>
          )}

          {error && (
            <div className="mt-8 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}{" "}
              <span className="text-muted-foreground">
                Ensure the API is running and <code className="rounded bg-muted px-1">GET /api/demo/snapshot</code> is reachable.
              </span>
            </div>
          )}

          {!loading && data && (
            <>
              <div className="mt-10 flex flex-wrap items-end gap-6">
                <div>
                  <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Escalation score</p>
                  <p className="font-mono text-5xl font-bold text-primary tabular-nums">
                    {data.escalation_score != null ? Math.round(data.escalation_score) : "–"}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Threat</p>
                  <Badge className={`mt-1 border ${threatClass(data.threat_level)}`}>{data.threat_level ?? "–"}</Badge>
                </div>
                <div className="min-w-[200px] flex-1">
                  <p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Theater</p>
                  <p className="mt-1 text-lg font-medium">{data.conflict}</p>
                </div>
              </div>

              {data.summary && (
                <section className="mt-10">
                  <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">BLUF</h2>
                  <p className="mt-3 text-base leading-relaxed text-foreground/95">{data.summary}</p>
                </section>
              )}

              {data.narrative_story && (
                <section className="mt-10">
                  <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Narrative</h2>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{data.narrative_story}</p>
                </section>
              )}

              {data.key_findings && data.key_findings.length > 0 && (
                <section className="mt-10">
                  <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Key findings</h2>
                  <ol className="mt-4 list-decimal space-y-3 pl-5 text-sm leading-relaxed">
                    {data.key_findings.map((k, i) => (
                      <li key={i}>
                        <div className="flex items-start gap-2">
                          <span className="text-foreground">{k}</span>
                          <FindingConfidenceBadge level={normalizeFindingConfidence(data.key_findings_confidence?.[i])} />
                        </div>
                        {data.key_findings_context?.[i] && (
                          <p className="mt-1 text-muted-foreground">{data.key_findings_context[i]}</p>
                        )}
                      </li>
                    ))}
                  </ol>
                </section>
              )}

              {data.verified_outcomes && data.verified_outcomes.length > 0 && (
                <section className="mt-10 rounded-lg border border-border bg-card/40 p-5">
                  <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Verified outcomes</h2>
                  <ul className="mt-3 space-y-3 text-sm">
                    {data.verified_outcomes.map((item, i) => (
                      <li key={i} className="rounded border border-border/70 p-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="outline" className="text-[10px] font-mono uppercase">
                            {item.verification_status ?? "verified"}
                          </Badge>
                          <FindingConfidenceBadge level={normalizeFindingConfidence(item.confidence)} />
                          {item.as_of && <span className="text-xs text-muted-foreground">as of {item.as_of}</span>}
                        </div>
                        {item.outcome && <p className="mt-2 text-foreground">{item.outcome}</p>}
                        {item.sources && item.sources.length > 0 && (
                          <p className="mt-1 text-xs text-muted-foreground">Sources: {item.sources.join(" | ")}</p>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {data.cross_validation && (
                <section className="mt-10 rounded-lg border border-border bg-card/40 p-5">
                  <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
                    Confidence pipeline
                  </h2>
                  <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
                    {data.cross_validation.pipeline_version && (
                      <Badge variant="outline" className="font-mono text-[10px] uppercase">
                        {data.cross_validation.pipeline_version}
                      </Badge>
                    )}
                    {data.cross_validation.overall_confidence && (
                      <FindingConfidenceBadge level={normalizeFindingConfidence(data.cross_validation.overall_confidence)} />
                    )}
                    {typeof data.cross_validation.checks_passed === "number" &&
                      typeof data.cross_validation.checks_total === "number" && (
                        <span className="text-muted-foreground">
                          {data.cross_validation.checks_passed}/{data.cross_validation.checks_total} checks passed
                        </span>
                      )}
                    {typeof data.cross_validation.consensus_score === "number" && (
                      <span className="text-muted-foreground">
                        consensus {Math.round(data.cross_validation.consensus_score * 100)}%
                      </span>
                    )}
                  </div>
                  {data.cross_validation.confidence_badges && data.cross_validation.confidence_badges.length > 0 && (
                    <ul className="mt-4 space-y-2 text-sm">
                      {data.cross_validation.confidence_badges.map((item, i) => (
                        <li key={i} className="rounded border border-border/70 p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge
                              variant="outline"
                              className={`text-[10px] font-mono uppercase ${
                                CHECK_BADGE[item.status ?? "watch"] ?? CHECK_BADGE.watch
                              }`}
                            >
                              {item.status ?? "watch"}
                            </Badge>
                            {item.confidence && (
                              <FindingConfidenceBadge level={normalizeFindingConfidence(item.confidence)} />
                            )}
                            <span className="font-medium text-foreground">{item.label ?? "Validation check"}</span>
                          </div>
                          {item.detail && <p className="mt-1 text-muted-foreground">{item.detail}</p>}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              )}

              {data.precomputed_agent_results && data.precomputed_agent_results.length > 0 && (
                <section className="mt-10 rounded-lg border border-border bg-card/40 p-5">
                  <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
                    Agent results
                  </h2>
                  <ul className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                    {data.precomputed_agent_results.map((r, i) => (
                      <li key={i} className="rounded border border-border/70 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-xs text-muted-foreground">{r.agent ?? "Agent"}</span>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm">{typeof r.score === "number" ? Math.round(r.score) : "-"}</span>
                            {r.confidence && <FindingConfidenceBadge level={normalizeFindingConfidence(r.confidence)} />}
                          </div>
                        </div>
                        {r.contribution && <p className="mt-1 text-muted-foreground">{r.contribution}</p>}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {data.proximity?.evidence && data.proximity.evidence.length > 0 && (
                <section className="mt-10 rounded-lg border border-border bg-card/40 p-5">
                  <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">Proximity (illustrative)</h2>
                  <ul className="mt-3 space-y-2 text-sm">
                    {data.proximity.evidence.slice(0, 4).map((ev, i) => (
                      <li key={i} className="border-l-2 border-primary/40 pl-3">
                        <span className="font-medium">{ev.facilityName}</span>
                        {ev.riskLabel && <span className="ml-2 text-xs text-muted-foreground">({ev.riskLabel})</span>}
                        {ev.summary && <p className="text-muted-foreground">{ev.summary}</p>}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <div className="mt-12 flex flex-wrap gap-3">
                <Button asChild>
                  <Link to="/app/dashboard">
                    Open live dashboard <ArrowRight className="ml-2 h-4 w-4" aria-hidden />
                  </Link>
                </Button>
                <Button variant="outline" asChild>
                  <Link to="/newsletter">Newsletter</Link>
                </Button>
              </div>
            </>
          )}
        </main>
      </div>
    </>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Loader2 } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiUrl } from "@/lib/api";
import type { AnalyzeResponse } from "@/lib/api";

type DemoPayload = AnalyzeResponse & {
  _demo?: boolean;
  scenario_id?: string;
  scenario_title?: string;
  scenario_note?: string;
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
        title="Curated demo – Digital War Room"
        description="Explore a curated Red Sea / Bab el-Mandeb scenario: escalation score, BLUF narrative, and multi-stream context–without live agent runs."
        path="/demo"
        imageAlt="Digital War Room demo snapshot"
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
          <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">Curated scenario</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
            {data?.scenario_title ?? "Maritime chokepoint demo"}
          </h1>
          {data?.scenario_note && (
            <p className="mt-3 text-sm text-muted-foreground">{data.scenario_note}</p>
          )}

          {loading && (
            <div className="mt-12 flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
              Loading snapshot…
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
                        <span className="text-foreground">{k}</span>
                        {data.key_findings_context?.[i] && (
                          <p className="mt-1 text-muted-foreground">{data.key_findings_context[i]}</p>
                        )}
                      </li>
                    ))}
                  </ol>
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

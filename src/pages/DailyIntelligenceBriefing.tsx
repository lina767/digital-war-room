import { useEffect, useState, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, FileDown, Share2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { getLatestAnalysis } from "@/lib/api";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { CONFLICT_OPTIONS } from "@/components/dashboard/conflictData";
import { SOURCE_DIRECTORY } from "@/lib/sourceDirectory";
import { differenceInDays } from "date-fns";

/** Reference start date for "Day X of operations" – counting from 28 February 2026. */
const OPERATIONS_START_DATE = new Date(2026, 1, 28); // 2026-02-28

function formatAsOf(date: Date): string {
  return date.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

function formatDateOnly(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export default function DailyIntelligenceBriefing() {
  const [searchParams] = useSearchParams();
  const conflictParam = searchParams.get("conflict") ?? CONFLICT_OPTIONS[0]?.apiValue ?? "Iran";
  const [data, setData] = useState<ConflictData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const printRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getLatestAnalysis(conflictParam)
      .then((res) => {
        setData(res as ConflictData | null);
      })
      .catch(() => setError("Failed to load briefing data."))
      .finally(() => setLoading(false));
  }, [conflictParam]);

  const handleSavePdf = () => {
    window.print();
  };

  const handleShare = async () => {
    const url = window.location.href;
    const title = "Daily Intelligence Briefing – Digital War Room";
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({
          title,
          url,
          text: `Daily Intelligence Briefing (${formatDateOnly(new Date())}). ${url}`,
        });
      } catch (err) {
        if ((err as Error).name !== "AbortError") copyToClipboard(url);
      }
    } else {
      copyToClipboard(url);
    }
  };

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text).then(() => {
      toast.success("Link copied to clipboard");
    });
  }

  const now = new Date();
  const dayOfOps = Math.max(1, differenceInDays(now, OPERATIONS_START_DATE) + 1);
  const conflictLabel = CONFLICT_OPTIONS.find((o) => o.apiValue === conflictParam)?.label ?? conflictParam;

  const globalImpactFindings = (data?.key_findings ?? []).filter((f) =>
    String(f).toLowerCase().includes("global impact")
  );
  const globalNote = data?.energy?.global_impact_note ?? null;

  const baselineForecast = data?.predictive?.baseline_escalation;
  const escalation24h =
    data?.predictive?.escalation?.find((f) => f.horizon === "24h") ??
    data?.predictive?.escalation?.[0];

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-10">
        {/* Top bar: back link + actions (hidden when printing) */}
        <div className="no-print mb-6 sm:mb-8 flex flex-wrap items-center justify-between gap-3">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to dashboard</span>
          </Link>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs"
              onClick={handleSavePdf}
              aria-label="Save as PDF"
            >
              <FileDown className="h-3.5 w-3.5" />
              Save as PDF
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs"
              onClick={handleShare}
              aria-label="Share"
            >
              <Share2 className="h-3.5 w-3.5" />
              Share
            </Button>
          </div>
        </div>

        {/* Printable content */}
        <div ref={printRef} id="daily-briefing-print" className="space-y-8">
          <header className="border-b border-border pb-6">
            <p className="font-mono text-[11px] sm:text-xs tracking-widest text-muted-foreground uppercase mb-2">
              DIGITAL WAR ROOM
            </p>
            <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight mb-4">
              Daily Intelligence Briefing
            </h1>
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground font-mono">
              <span>Date: {formatDateOnly(now)}</span>
              <span>As of: {formatAsOf(now)}</span>
              <span>Day {dayOfOps} of operations</span>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Conflict focus: {conflictLabel}
            </p>
          </header>

          {loading && (
            <p className="text-sm text-muted-foreground italic">Loading briefing data…</p>
          )}
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
          {!loading && !error && data && (
            <div className="space-y-8">
              {/* 1. Executive Summary */}
              <section>
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  1. Executive Summary
                </h2>
                <div className="rounded-lg border border-border bg-card/50 p-4 text-sm leading-relaxed">
                  {data.summary ? (
                    <p>{data.summary}</p>
                  ) : (
                    <p className="text-muted-foreground italic">No executive summary available for this period.</p>
                  )}
                </div>
              </section>

              {/* 2. Key Developments of Day X */}
              <section>
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  2. Key Developments of Day {dayOfOps}
                </h2>
                <div className="rounded-lg border border-border bg-card/50 p-4">
                  {(data.key_findings?.length ?? 0) > 0 ? (
                    <ul className="space-y-2 text-sm">
                      {data.key_findings!.map((f, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="text-primary shrink-0">•</span>
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (data.news?.articles?.length ?? 0) > 0 ? (
                    <ul className="space-y-2 text-sm">
                      {data.news!.articles!.slice(0, 10).map((a, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="text-primary shrink-0">•</span>
                          <span>{a.title ?? "—"}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground italic">No key developments recorded for this day.</p>
                  )}
                </div>
              </section>

              {/* 3. Predictive Outlook */}
              <section>
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  3. Predictive Outlook
                </h2>
                <div className="rounded-lg border border-border bg-card/50 p-4 text-sm leading-relaxed space-y-3">
                  {!baselineForecast && !escalation24h && (
                    <p className="text-muted-foreground italic">
                      No predictive outlook available for this period.
                    </p>
                  )}
                  {baselineForecast && (
                    <div>
                      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-0.5">
                        Baseline (null hypothesis)
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Expected escalation level without current signals:
                        {" "}
                        <span className="font-mono text-foreground">{baselineForecast.level}</span>
                        {baselineForecast.range && (
                          <>
                            {" "}
                            (band{" "}
                            <span className="font-mono">
                              {Math.round(baselineForecast.range.min * 100)}–{Math.round(baselineForecast.range.max * 100)}%
                            </span>
                            ).
                          </>
                        )}
                      </p>
                    </div>
                  )}
                  {escalation24h && (
                    <div>
                      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-0.5">
                        Escalation – {escalation24h.horizon}
                      </p>
                      <p className="text-xs">
                        Level:
                        {" "}
                        <span className="font-mono">{escalation24h.level}</span>
                        {escalation24h.range && (
                          <>
                            {" "}
                            (band{" "}
                            <span className="font-mono">
                              {Math.round(escalation24h.range.min * 100)}–{Math.round(escalation24h.range.max * 100)}%
                            </span>
                            ).
                          </>
                        )}
                        {baselineForecast && (
                          <>
                            {" "}
                            Relative to baseline:
                            {" "}
                            <span className="font-mono uppercase text-muted-foreground">
                              {escalation24h.vs_baseline}
                            </span>
                            .
                          </>
                        )}
                      </p>
                      {escalation24h.drivers && escalation24h.drivers.length > 0 && (
                        <ul className="mt-1 space-y-0.5">
                          {escalation24h.drivers.slice(0, 3).map((d, i) => (
                            <li key={i} className="text-xs text-muted-foreground flex gap-1.5">
                              <span className="mt-[6px] h-1 w-1 rounded-full bg-primary/80 flex-shrink-0" />
                              <span>{d}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                  <p className="text-[10px] text-muted-foreground">
                    Levels and bands are coarse indicators derived from existing agent scores and a conflict-specific baseline.
                    They are not precise probabilities.
                  </p>
                </div>
              </section>

              {/* 4. Global Impact */}
              <section>
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  4. Global Impact
                </h2>
                <div className="rounded-lg border border-border bg-card/50 p-4 text-sm leading-relaxed">
                  {globalNote && <p className="mb-3">{globalNote}</p>}
                  {globalImpactFindings.length > 0 ? (
                    <ul className="space-y-1.5">
                      {globalImpactFindings.map((f, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="text-primary shrink-0">•</span>
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                  ) : !globalNote && (
                    <p className="text-muted-foreground italic">No global impact assessment for this period.</p>
                  )}
                </div>
              </section>

              {/* 5. Things to Watch */}
              <section>
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  5. Things to Watch
                </h2>
                <div className="rounded-lg border border-border bg-card/50 p-4">
                  {(data.scenarios?.length ?? 0) > 0 ? (
                    <ol className="space-y-2 text-sm list-decimal list-inside">
                      {data.scenarios!.map((s, i) => (
                        <li key={i}>
                          <span className="font-medium">{s.description}</span>
                          {typeof s.probability === "number" && (
                            <span className="text-muted-foreground ml-1">
                              ({Math.round(s.probability * 100)}%)
                            </span>
                          )}
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="text-sm text-muted-foreground italic">No scenarios on watch for this period.</p>
                  )}
                </div>
              </section>

              {/* 6. Sanctions Compliance */}
              <section>
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  6. Sanctions Compliance
                </h2>
                <div className="rounded-lg border border-border bg-card/50 p-4 text-sm leading-relaxed space-y-3">
                  {/* Risk Score */}
                  {data.compliance?.risk_score && (
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-muted-foreground">Compliance Risk:</span>
                      <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
                        data.compliance.risk_score.level === "CRITICAL" ? "bg-destructive text-destructive-foreground"
                        : data.compliance.risk_score.level === "HIGH" ? "bg-orange-500/90 text-black"
                        : data.compliance.risk_score.level === "MEDIUM" ? "bg-yellow-400/80 text-black"
                        : "bg-emerald-500/80 text-black"
                      }`}>
                        {data.compliance.risk_score.level}
                      </span>
                      <span className="text-xs text-muted-foreground font-mono">
                        {data.compliance.risk_score.numeric_score}/100
                      </span>
                    </div>
                  )}

                  {/* Risk Drivers */}
                  {(data.compliance?.risk_score?.drivers?.length ?? 0) > 0 &&
                    data.compliance!.risk_score!.drivers[0].factor !== "NO_SIGNALS" && (
                    <div>
                      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1">
                        Risk Drivers
                      </p>
                      <ul className="space-y-1.5">
                        {data.compliance!.risk_score!.drivers.map((d, i) => (
                          <li key={i} className="flex gap-2 text-xs">
                            <span className="text-primary shrink-0 mt-0.5">-</span>
                            <div>
                              <span>
                                <span className="font-mono text-muted-foreground">[{d.factor}]</span>{" "}
                                {d.detail}
                                <span className="text-muted-foreground ml-1">({d.impact})</span>
                              </span>
                              {(d as any).programs && (
                                <p className="text-[10px] text-muted-foreground/70 mt-0.5">
                                  Programs: {(d as any).programs}
                                </p>
                              )}
                              {(d as any).note && (
                                <p className="text-[10px] text-muted-foreground/60 mt-0.5 italic">
                                  {(d as any).note}
                                </p>
                              )}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* OFAC / EU Sanctions Data */}
                  {((data.compliance?.ofac_sdn?.total_matches ?? 0) > 0 || (data.compliance?.eu_sanctions?.keyword_mentions ?? 0) > 0) && (
                    <div>
                      <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1">
                        Sanctions Lists
                      </p>
                      <ul className="space-y-1 text-xs">
                        {(data.compliance?.ofac_sdn?.total_matches ?? 0) > 0 && (
                          <li className="flex gap-2">
                            <span className="text-orange-400 shrink-0">SDN</span>
                            <span>
                              <span className="font-semibold">{data.compliance!.ofac_sdn!.total_matches}</span>{" "}
                              OFAC SDN entries match conflict entities
                              {(data.compliance!.ofac_sdn!.sample?.length ?? 0) > 0 && (
                                <span className="text-muted-foreground">
                                  {" "}(e.g. {data.compliance!.ofac_sdn!.sample!.slice(0, 3).map(s => s.name).join(", ")})
                                </span>
                              )}
                            </span>
                          </li>
                        )}
                        {(data.compliance?.eu_sanctions?.keyword_mentions ?? 0) > 0 && (
                          <li className="flex gap-2">
                            <span className="text-blue-400 shrink-0">EU</span>
                            <span>
                              <span className="font-semibold">{data.compliance!.eu_sanctions!.keyword_mentions}</span>{" "}
                              keyword mentions in EU consolidated sanctions list
                            </span>
                          </li>
                        )}
                      </ul>
                    </div>
                  )}

                  {/* Geofencing */}
                  {(data.compliance?.geofencing_alerts?.length ?? 0) > 0 ? (
                    <>
                      <p>
                        <span className="font-semibold">{data.compliance!.geofencing_alerts!.length}</span> geofencing alert(s):
                      </p>
                      <ul className="space-y-1">
                        {data.compliance!.geofencing_alerts!.slice(0, 10).map((a, i) => (
                          <li key={i} className="flex gap-2 text-xs">
                            <span className="text-orange-400 shrink-0">W</span>
                            <span>
                              <span className="font-mono">{a.asset_name}</span> ({a.asset_type}) in{" "}
                              <span className="font-mono">{(a.zone_name || "").replace(/_/g, " ")}</span>{" "}
                              <span className="text-muted-foreground">({a.zone_type})</span>
                            </span>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <p className="text-muted-foreground italic text-xs">No geofencing alerts in current SIGINT window.</p>
                  )}

                  {/* AIS Anomalies */}
                  {(data.compliance?.ais_anomalies?.length ?? 0) > 0 && (
                    <>
                      <p className="text-xs">
                        <span className="font-semibold">{data.compliance!.ais_anomalies!.length}</span> AIS anomal(y/ies) detected:
                      </p>
                      <ul className="space-y-1">
                        {data.compliance!.ais_anomalies!.slice(0, 5).map((a, i) => (
                          <li key={i} className="flex gap-2 text-xs">
                            <span className={a.anomaly_type === "spoofing" ? "text-red-400 shrink-0" : "text-purple-400 shrink-0"}>
                              {a.anomaly_type === "spoofing" ? "!" : "O"}
                            </span>
                            <span>
                              <span className="font-mono">{a.asset_name}</span>: {a.detail}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}

                  <p className="text-[10px] text-muted-foreground pt-1 border-t border-border/50">
                    Intelligence signals only – not legal advice. Supports due diligence but does not replace legal review.
                  </p>
                </div>
              </section>

              {/* 7. Sources */}
              <section>
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  7. Sources
                </h2>
                <div className="rounded-lg border border-border bg-card/50 p-4">
                  <p className="text-xs text-muted-foreground mb-3">
                    This briefing is generated from the following data sources used by the platform agents.
                  </p>
                  <ul className="text-sm space-y-1 columns-1 sm:columns-2 gap-4">
                    {SOURCE_DIRECTORY.map((s) => (
                      <li key={s.id} className="break-inside-avoid">
                        {s.name}
                        {s.agents.length > 0 && (
                          <span className="text-muted-foreground text-xs ml-1">
                            ({s.agents.join(", ")})
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </section>
            </div>
          )}

          {!loading && !error && !data && (
            <p className="text-sm text-muted-foreground">
              No cached analysis available. Run an analysis from the dashboard for {conflictLabel}, then return here for
              the daily briefing.
            </p>
          )}
        </div>
      </div>

      {/* Print styles: hide non-print elements */}
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: white; color: black; }
          #daily-briefing-print { max-width: 100%; }
        }
      `}</style>
    </div>
  );
}

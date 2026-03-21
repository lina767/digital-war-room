import { useEffect, useState, useRef, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, FileDown, RefreshCw, Share2, WifiOff } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { getLatestAnalysis } from "@/lib/api";
import type { ConflictData } from "@/hooks/useConflictWebSocket";
import { CONFLICT_OPTIONS } from "@/components/dashboard/conflictData";
import { cn } from "@/lib/utils";
import {
  PREDICTIVE_OUTLOOK_DISCLAIMER,
  PREDICTIVE_OUTLOOK_INTRO_SHORT,
} from "@/lib/predictiveOutlookCopy";
import { COMPLIANCE_DISCLAIMER, COMPLIANCE_INTRO_SHORT } from "@/lib/complianceCopy";
import { SOURCE_DIRECTORY } from "@/lib/sourceDirectory";
import { differenceInDays } from "date-fns";
import { Skeleton } from "@/components/ui/skeleton";
import { FindingConfidenceBadge, normalizeFindingConfidence } from "@/components/dashboard/FindingConfidenceBadge";
import { RootCauseSuggestions } from "@/components/dashboard/RootCauseSuggestions";
import { NarrativeBody } from "@/components/dashboard/NarrativeBody";
import { SEO } from "@/components/SEO";
import {
  TITLE_DAILY_BRIEFING,
  DESCRIPTION_DAILY_BRIEFING,
  SHARE_TITLE_DAILY_BRIEFING,
  STRUCTURED_DESC_DAILY_BRIEFING,
} from "@/lib/seoCopy";

/** Reference start date for "Day X of operations" – counting from 28 February 2026. */
const OPERATIONS_START_DATE = new Date(2026, 1, 28); // 2026-02-28

function formatAsOf(date: Date): string {
  return date.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

function formatDateOnly(date: Date): string {
  return date.toISOString().slice(0, 10);
}

const BRIEFING_NAV = [
  { href: "#briefing-summary", label: "Summary" },
  { href: "#briefing-developments", label: "Developments" },
  { href: "#briefing-predictive", label: "Outlook" },
  { href: "#briefing-global", label: "Global" },
  { href: "#briefing-watch", label: "Watch" },
  { href: "#briefing-compliance", label: "Compliance" },
  { href: "#briefing-sources", label: "Sources" },
] as const;

export default function DailyIntelligenceBriefing() {
  const [searchParams, setSearchParams] = useSearchParams();
  const conflictParam = searchParams.get("conflict") ?? CONFLICT_OPTIONS[0]?.apiValue ?? "Iran";
  const [data, setData] = useState<ConflictData | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const printRef = useRef<HTMLDivElement>(null);

  const loadBriefing = useCallback(() => {
    setLoading(true);
    setError(null);
    getLatestAnalysis(conflictParam)
      .then((result) => {
        setData(result.data as ConflictData | null);
        setFromCache(result.fromCache);
      })
      .catch((err) => {
        setData(null);
        setFromCache(false);
        setError(err instanceof Error ? err.message : "Failed to load briefing data.");
      })
      .finally(() => setLoading(false));
  }, [conflictParam]);

  useEffect(() => {
    loadBriefing();
  }, [loadBriefing]);

  const handleSavePdf = () => {
    window.print();
  };

  const handleShare = async () => {
    const url = window.location.href;
    const title = SHARE_TITLE_DAILY_BRIEFING;
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

  const handleConflictChange = (value: string) => {
    setSearchParams({ conflict: value }, { replace: true });
  };

  const globalImpactFindings = (data?.key_findings ?? []).filter((f) =>
    String(f).toLowerCase().includes("global impact")
  );
  const globalNote = data?.energy?.global_impact_note ?? null;

  const baselineForecast = data?.predictive?.baseline_escalation;
  const escalationList = data?.predictive?.escalation ?? [];
  const escalation24h = escalationList.find((f) => f.horizon === "24h") ?? escalationList[0];
  const escalation7d = escalationList.find((f) => f.horizon === "7d");
  const escalationForecasts = [escalation24h, escalation7d].filter(Boolean) as typeof escalationList;

  const dailyBriefingStructuredData = {
    "@type": "Report",
    "@id": "https://digital-war-room.com/daily-briefing#report",
    name: SHARE_TITLE_DAILY_BRIEFING,
    url: "https://digital-war-room.com/daily-briefing",
    datePublished: formatDateOnly(now),
    dateModified: formatDateOnly(now),
    description: STRUCTURED_DESC_DAILY_BRIEFING,
  };

  return (
    <>
      <SEO
        title={TITLE_DAILY_BRIEFING}
        description={DESCRIPTION_DAILY_BRIEFING}
        path="/daily-briefing"
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Daily Briefing", url: "https://digital-war-room.com/daily-briefing" },
        ]}
        structuredData={dailyBriefingStructuredData}
      />
      <div className="min-h-screen bg-background text-foreground">
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-10">
        {/* Top bar: back link + actions (hidden when printing) */}
        <div className="no-print mb-6 sm:mb-8 flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to dashboard</span>
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
              <span className="sr-only">Conflict focus</span>
              <span aria-hidden className="hidden sm:inline">
                Focus
              </span>
              <select
                className={cn(
                  "h-9 min-w-[140px] rounded-md border border-border bg-card/80 px-2.5 py-1 text-sm font-mono text-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
                )}
                value={conflictParam}
                onChange={(e) => handleConflictChange(e.target.value)}
                aria-label="Conflict focus for this briefing"
              >
                {!CONFLICT_OPTIONS.some((o) => o.apiValue === conflictParam) && (
                  <option value={conflictParam}>{conflictLabel}</option>
                )}
                {CONFLICT_OPTIONS.map((o) => (
                  <option key={o.id} value={o.apiValue}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs"
              onClick={handleSavePdf}
              aria-label="Save as PDF"
            >
              <FileDown className="h-3.5 w-3.5" aria-hidden />
              Save as PDF
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs"
              onClick={handleShare}
              aria-label="Share"
            >
              <Share2 className="h-3.5 w-3.5" aria-hidden />
              Share
            </Button>
          </div>
        </div>

        {/* Printable content */}
        <div ref={printRef} id="daily-briefing-print" className="space-y-8">
          <header className="border-b border-border pb-6 print:border-neutral-300">
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

          {fromCache && !loading && data && (
            <div
              className="no-print flex items-center gap-2 rounded-lg border border-amber-500/35 bg-amber-500/10 px-3 py-2 text-xs text-amber-200/90"
              role="status"
            >
              <WifiOff className="h-3.5 w-3.5 shrink-0 opacity-90" aria-hidden />
              <span>Showing cached analysis (offline or API unavailable). Reconnect and retry load for the latest.</span>
            </div>
          )}

          <nav
            className="no-print flex flex-wrap gap-1.5 border-b border-border/60 pb-4 -mb-2"
            aria-label="Briefing sections"
          >
            {BRIEFING_NAV.map(({ href, label }) => (
              <a
                key={href}
                href={href}
                className="rounded-md border border-transparent px-2 py-1 text-[11px] font-mono text-muted-foreground hover:border-border hover:bg-card/60 hover:text-foreground transition-colors"
              >
                {label}
              </a>
            ))}
          </nav>

          {loading && (
            <div className="space-y-4" aria-busy="true" aria-live="polite">
              <Skeleton className="h-6 w-2/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-20 w-full rounded-lg" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-4/5" />
            </div>
          )}
          {error && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <p className="text-sm text-destructive">{error}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5 shrink-0 border-destructive/40"
                onClick={() => loadBriefing()}
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden />
                Retry
              </Button>
            </div>
          )}
          {!loading && !error && data && (
            <div className="space-y-8">
              {(data.escalation_score != null || data.threat_level) && (
                <div className="flex flex-wrap gap-3">
                  {data.threat_level != null && data.threat_level !== "" && (
                    <div className="rounded-lg border border-border bg-card/60 px-3 py-2 min-w-[120px]">
                      <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-0.5">
                        Threat level
                      </p>
                      <p className="text-sm font-semibold font-mono">{data.threat_level}</p>
                    </div>
                  )}
                  {data.escalation_score != null && (
                    <div className="rounded-lg border border-border bg-card/60 px-3 py-2 min-w-[120px]">
                      <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground mb-0.5">
                        Escalation score
                      </p>
                      <p className="text-sm font-semibold font-mono tabular-nums">
                        {Math.round(Number(data.escalation_score))}
                        <span className="text-muted-foreground font-normal text-xs ml-1">/ 100</span>
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* 1. Executive Summary */}
              <section id="briefing-summary" className="scroll-mt-24 print:break-inside-avoid">
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  1. Executive Summary
                </h2>
                <div className="space-y-4">
                  <div className="rounded-lg border border-border bg-card/50 p-4 text-sm leading-relaxed">
                    {data.summary ? (
                      <p className="text-pretty">{data.summary}</p>
                    ) : (
                      <p className="text-muted-foreground italic">No executive summary available for this period.</p>
                    )}
                  </div>
                  {(data.root_cause_suggestions?.length ?? 0) > 0 && (
                    <RootCauseSuggestions items={data.root_cause_suggestions!} />
                  )}
                  {data.narrative_story != null && String(data.narrative_story).trim() !== "" && (
                    <div className="rounded-lg border border-border bg-card/40 p-4">
                      <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">
                        Cross-stream narrative
                      </p>
                      <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
                        Operational story: how the main intelligence lines connect, reinforce, or contradict — the beat
                        after the executive summary.
                      </p>
                      <NarrativeBody text={String(data.narrative_story)} />
                    </div>
                  )}
                </div>
              </section>

              {/* 2. Key Developments of Day X */}
              <section id="briefing-developments" className="scroll-mt-24 print:break-inside-avoid">
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  2. Key Developments of Day {dayOfOps}
                </h2>
                <div className="rounded-lg border border-border bg-card/50 p-4">
                  {(data.key_findings?.length ?? 0) > 0 ? (
                    <ul className="space-y-3 text-sm">
                      {data.key_findings!.map((f, i) => (
                        <li key={i} className="flex flex-col gap-1">
                          <div className="flex gap-2 items-start">
                            <FindingConfidenceBadge
                              className="mt-0.5"
                              level={normalizeFindingConfidence(data.key_findings_confidence?.[i])}
                            />
                            <span className="text-primary shrink-0 pt-0.5">•</span>
                            <span className="text-pretty min-w-0">{f}</span>
                          </div>
                          {data.key_findings_context?.[i] != null && String(data.key_findings_context[i]).trim() !== "" && (
                            <p className="pl-5 text-xs text-muted-foreground border-l-2 border-border/70 leading-relaxed">
                              {data.key_findings_context[i]}
                            </p>
                          )}
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
                {(data.corroborated_patterns?.length ?? 0) > 0 && (
                  <div className="mt-4 rounded-lg border border-primary/25 bg-primary/5 p-4 space-y-2">
                    <p className="text-[11px] font-mono text-primary/90 uppercase tracking-wider">
                      Corroborated patterns
                    </p>
                    <ul className="space-y-2 text-sm">
                      {data.corroborated_patterns!.slice(0, 6).map((p, i) => (
                        <li key={p.pattern_id ?? i} className="text-pretty">
                          {p.summary != null && p.summary !== "" ? (
                            <span>{p.summary}</span>
                          ) : (
                            <span className="text-muted-foreground italic">Pattern {i + 1}</span>
                          )}
                          {Array.isArray(p.agent_ids) && p.agent_ids.length > 0 && (
                            <span className="block text-[11px] text-muted-foreground mt-0.5 font-mono">
                              Agents: {p.agent_ids.join(", ")}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>

              {/* 3. Predictive Outlook */}
              <section id="briefing-predictive" className="scroll-mt-24 print:break-inside-avoid">
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  3. Predictive Outlook
                </h2>
                <div className="rounded-lg border border-border bg-card/50 p-4 text-sm leading-relaxed space-y-3">
                  <p className="text-xs text-muted-foreground">
                    {PREDICTIVE_OUTLOOK_INTRO_SHORT}
                  </p>
                  {!baselineForecast && escalationForecasts.length === 0 && (
                    <p className="text-muted-foreground italic">
                      No predictive outlook available for this period.
                    </p>
                  )}
                  {baselineForecast && (
                    <div>
                      <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-0.5">
                        Baseline (null hypothesis)
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Expected escalation level without current signals (what you’d expect if there were no new signals):
                        {" "}
                        <span className="font-mono text-foreground">{baselineForecast.level}</span>
                        {baselineForecast.range && (
                          <>
                            {" "}
                            (band{" "}
                            <span className="font-mono">
                              {Math.round(baselineForecast.range.min * 100)}–{Math.round(baselineForecast.range.max * 100)}%
                            </span>
                            {" "}
                            – rough probability range).
                          </>
                        )}
                      </p>
                      {baselineForecast.drivers && baselineForecast.drivers.length > 0 && (
                        <ul className="mt-1 space-y-0.5">
                          {baselineForecast.drivers.map((d, i) => (
                            <li key={i} className="text-xs text-muted-foreground flex gap-1.5">
                              <span className="mt-[6px] h-1 w-1 rounded-full bg-muted-foreground/60 flex-shrink-0" />
                              <span>{d}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                  {escalationForecasts.map((forecast) => (
                    <div key={forecast.horizon}>
                      <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-0.5">
                        Escalation – {forecast.horizon}
                        {forecast.confidence && (
                          <span className="ml-2 font-sans normal-case text-muted-foreground">
                            (confidence: {forecast.confidence})
                          </span>
                        )}
                      </p>
                      <p className="text-xs">
                        Level:
                        {" "}
                        <span className="font-mono">{forecast.level}</span>
                        {forecast.range && (
                          <>
                            {" "}
                            (band{" "}
                            <span className="font-mono">
                              {Math.round(forecast.range.min * 100)}–{Math.round(forecast.range.max * 100)}%
                            </span>
                            {" "}
                            – rough range).
                          </>
                        )}
                        {baselineForecast && (
                          <>
                            {" "}
                            Relative to baseline:
                            {" "}
                            <span className="font-mono uppercase text-muted-foreground">
                              {forecast.vs_baseline}
                            </span>
                            .
                          </>
                        )}
                      </p>
                      {forecast.notes && (
                        <p className="text-[11px] text-muted-foreground/80 italic mt-0.5">
                          {forecast.notes}
                        </p>
                      )}
                      {forecast.drivers && forecast.drivers.length > 0 && (
                        <ul className="mt-1 space-y-0.5">
                          {forecast.drivers.slice(0, 3).map((d, i) => (
                            <li key={i} className="text-xs text-muted-foreground flex gap-1.5">
                              <span className="mt-[6px] h-1 w-1 rounded-full bg-primary/80 flex-shrink-0" />
                              <span>{d}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                  <p className="text-[11px] text-muted-foreground">
                    {PREDICTIVE_OUTLOOK_DISCLAIMER}
                  </p>
                </div>
              </section>

              {/* 4. Global Impact */}
              <section id="briefing-global" className="scroll-mt-24 print:break-inside-avoid">
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
              <section id="briefing-watch" className="scroll-mt-24 print:break-inside-avoid">
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
              <section id="briefing-compliance" className="scroll-mt-24 print:break-inside-avoid">
                <h2 className="font-mono text-xs text-muted-foreground tracking-wider uppercase mb-2">
                  6. Sanctions Compliance
                </h2>
                <div className="rounded-lg border border-border bg-card/50 p-4 text-sm leading-relaxed space-y-3">
                  <p className="text-sm text-muted-foreground">{COMPLIANCE_INTRO_SHORT}</p>
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
                    data.compliance?.risk_score?.drivers?.[0]?.factor !== "NO_SIGNALS" && (
                    <div>
                      <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">
                        Risk Drivers
                      </p>
                      <ul className="space-y-1.5">
                        {(data.compliance?.risk_score?.drivers ?? []).map((d, i) => (
                          <li key={i} className="flex gap-2 text-xs">
                            <span className="text-primary shrink-0 mt-0.5">-</span>
                            <div>
                              <span>
                                <span className="font-mono text-muted-foreground">[{d.factor}]</span>{" "}
                                {d.detail}
                                <span className="text-muted-foreground ml-1">({d.impact})</span>
                              </span>
                              {d.programs && (
                                <p className="text-[11px] text-muted-foreground/70 mt-0.5">
                                  Programs: {d.programs}
                                </p>
                              )}
                              {d.note && (
                                <p className="text-[11px] text-muted-foreground/60 mt-0.5 italic">
                                  {d.note}
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
                      <p className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider mb-1">
                        Sanctions Lists
                      </p>
                      <ul className="space-y-1 text-xs">
                        {(data.compliance?.ofac_sdn?.total_matches ?? 0) > 0 && (
                          <li className="flex gap-2">
                            <span className="text-orange-400 shrink-0">SDN</span>
                            <div>
                              <span>
                                <span className="font-semibold">{data.compliance?.ofac_sdn?.total_matches}</span>{" "}
                                OFAC SDN entries match conflict entities
                                {(data.compliance?.ofac_sdn?.sample?.length ?? 0) > 0 && (
                                  <span className="text-muted-foreground">
                                    {" "}(e.g. {(data.compliance?.ofac_sdn?.sample ?? []).slice(0, 3).map(s => s.name).join(", ")})
                                  </span>
                                )}
                              </span>
                              {(data.compliance?.ofac_sdn?.programs?.length ?? 0) > 0 && (
                                <p className="text-[11px] text-muted-foreground mt-0.5">
                                  Programs: {(data.compliance?.ofac_sdn?.programs ?? []).slice(0, 6).map(p => `${p.name} (${p.count})`).join(", ")}
                                </p>
                              )}
                            </div>
                          </li>
                        )}
                        {(data.compliance?.eu_sanctions?.keyword_mentions ?? 0) > 0 && (
                          <li className="flex gap-2">
                            <span className="text-blue-400 shrink-0">EU</span>
                            <span>
                              <span className="font-semibold">{data.compliance?.eu_sanctions?.keyword_mentions}</span>{" "}
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
                        <span className="font-semibold">{data.compliance?.geofencing_alerts?.length}</span> geofencing alert(s):
                      </p>
                      <ul className="space-y-1">
                        {(data.compliance?.geofencing_alerts ?? []).slice(0, 10).map((a, i) => (
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
                        <span className="font-semibold">{data.compliance?.ais_anomalies?.length}</span> AIS anomal(y/ies) detected:
                      </p>
                      <ul className="space-y-1">
                        {(data.compliance?.ais_anomalies ?? []).slice(0, 5).map((a, i) => (
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

                  <p className="text-[11px] text-muted-foreground pt-1 border-t border-border/50">
                    {COMPLIANCE_DISCLAIMER}
                  </p>
                </div>
              </section>

              {/* 7. Sources */}
              <section id="briefing-sources" className="scroll-mt-24 print:break-inside-avoid">
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
            <div className="rounded-xl border border-border bg-card/40 p-6 text-center space-y-3">
              <p className="text-sm text-muted-foreground max-w-md mx-auto">
                No cached analysis for <span className="font-mono text-foreground">{conflictLabel}</span> yet. Run or
                refresh an analysis from the dashboard, then open this page again.
              </p>
              <Button asChild variant="default" size="sm" className="font-mono text-xs">
                <Link to="/">Open dashboard</Link>
              </Button>
            </div>
          )}

          <p className="no-print mt-8 pt-6 border-t border-border text-sm text-muted-foreground">
            Get the daily briefing by email —{" "}
            <Link to="/newsletter" className="text-primary hover:underline">
              Subscribe to daily briefing
            </Link>
          </p>
        </div>
      </main>

      {/* Print styles: hide non-print elements */}
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: white !important; color: #111 !important; }
          #daily-briefing-print { max-width: 100%; }
          #daily-briefing-print a { color: #0b57d0 !important; text-decoration: underline; }
          #daily-briefing-print .rounded-lg, #daily-briefing-print .rounded-xl { border-color: #ccc !important; background: #fafafa !important; }
        }
      `}</style>
    </div>
    </>
  );
}

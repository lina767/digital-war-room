import { Link, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useRef } from "react";
import { toast } from "sonner";
import { ArrowLeft, Loader2 } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentDeepDives } from "@/features/daily-briefing/components/AgentDeepDives";
import { AgentStatusPanel } from "@/features/daily-briefing/components/AgentStatusPanel";
import { BLUFSection } from "@/features/daily-briefing/components/BLUFSection";
import { BriefingFooter } from "@/features/daily-briefing/components/BriefingFooter";
import { BriefingHeader } from "@/features/daily-briefing/components/BriefingHeader";
import { ChokepointStatus } from "@/features/daily-briefing/components/ChokepointStatus";
import { KeyFindings } from "@/features/daily-briefing/components/KeyFindings";
import { MarketSnapshot } from "@/features/daily-briefing/components/MarketSnapshot";
import { PredictiveOutlook } from "@/features/daily-briefing/components/PredictiveOutlook";
import { ScenarioAssessment } from "@/features/daily-briefing/components/ScenarioAssessment";
import { useBriefingData } from "@/features/daily-briefing/hooks/useBriefingData";
import { useBriefingExport } from "@/features/daily-briefing/hooks/useBriefingExport";
import {
  DESCRIPTION_DAILY_BRIEFING,
  SHARE_TITLE_DAILY_BRIEFING,
  STRUCTURED_DESC_DAILY_BRIEFING,
  TITLE_DAILY_BRIEFING,
} from "@/lib/seoCopy";
import {
  getUtmContext,
  markNewsletterTouchNow,
  shouldCountAs24hReturn,
  trackKpiEvent,
} from "@/lib/briefingKpiTracking";

const NAV_ITEMS = [
  { id: "briefing-start-here", label: "Start Here" },
  { id: "briefing-summary", label: "Summary" },
  { id: "briefing-infographic", label: "Infographic" },
  { id: "briefing-developments", label: "Findings" },
  { id: "briefing-predictive", label: "Outlook" },
  { id: "briefing-global", label: "Global" },
  { id: "briefing-watch", label: "Things to Watch" },
  { id: "briefing-sources", label: "Deep Dives" },
];

interface TopAction {
  id: string;
  title: string;
  rationale: string;
  target: string;
  cta: string;
}

function buildTopActions(escalationScore: number, findingsCount: number, chokepointsCount: number): TopAction[] {
  const actions: TopAction[] = [
    {
      id: "action-findings",
      title: "Triage highest-signal findings",
      rationale:
        findingsCount > 0
          ? `Review the top ${Math.min(3, findingsCount)} findings and validate confidence before escalation decisions.`
          : "No findings yet - trigger a fresh run, then review first-order signal changes.",
      target: "#briefing-developments",
      cta: "Open findings",
    },
    {
      id: "action-chokepoints",
      title: "Check chokepoint risk exposure",
      rationale:
        chokepointsCount > 0
          ? "Confirm whether shipping risk changes require route or sourcing adjustments."
          : "No chokepoint anomalies surfaced yet; monitor for late-cycle disruptions.",
      target: "#briefing-watch",
      cta: "Open chokepoints",
    },
    {
      id: "action-outlook",
      title: "Align next-24h operating posture",
      rationale:
        escalationScore >= 70
          ? "Escalation is high - tighten monitoring cadence and pre-brief stakeholders."
          : "Use outlook drivers to set monitoring intensity for the next 24 hours.",
      target: "#briefing-predictive",
      cta: "Open outlook",
    },
  ];
  return actions;
}

export default function DailyBriefingPage() {
  const [searchParams] = useSearchParams();
  const { state, dispatch, meta } = useBriefingData();
  const exportPdf = useBriefingExport();
  const data = state.data;
  const showLoading = !data && (meta.initialLoadPending || state.isLoading);
  const showError = !data && state.error && !showLoading;
  const firstInteractionTrackedRef = useRef(false);
  const pageLoadedAtRef = useRef<number | null>(null);

  const utm = useMemo(() => getUtmContext(), [searchParams]);

  useEffect(() => {
    const section = searchParams.get("nl_section");
    if (!section) return;
    const el = document.getElementById(section);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [searchParams, data]);

  useEffect(() => {
    if (showLoading || !data) return;
    if (pageLoadedAtRef.current == null) {
      pageLoadedAtRef.current = Date.now();
    }
    if (utm.source === "newsletter") {
      markNewsletterTouchNow();
      trackKpiEvent("newsletter_slot_click", {
        conflict: data.conflict,
        campaign: utm.campaign,
        utmContent: utm.utmContent,
      });
    }
    if (shouldCountAs24hReturn()) {
      trackKpiEvent("return_24h_after_newsletter", {
        conflict: data.conflict,
        campaign: utm.campaign,
        utmContent: utm.utmContent,
      });
    }
  }, [showLoading, data, utm.source, utm.campaign, utm.utmContent]);

  const markMeaningfulInteraction = (eventName: string): void => {
    if (!data) return;
    if (!firstInteractionTrackedRef.current) {
      firstInteractionTrackedRef.current = true;
      const startedAt = pageLoadedAtRef.current;
      if (startedAt != null) {
        const ttvSeconds = Math.max(0, (Date.now() - startedAt) / 1000);
        trackKpiEvent("ttv_recorded", {
          conflict: data.conflict,
          campaign: utm.campaign,
          utmContent: utm.utmContent,
          ttvSeconds,
        });
      }
    }
    trackKpiEvent(eventName, {
      conflict: data.conflict,
      campaign: utm.campaign,
      utmContent: utm.utmContent,
    });
  };

  const share = async () => {
    const url = window.location.href;
    if (typeof navigator.share === "function") {
      await navigator.share({ title: SHARE_TITLE_DAILY_BRIEFING, url });
      return;
    }
    await navigator.clipboard.writeText(url);
    toast.success("Briefing link copied");
  };

  if (showLoading) {
    return (
      <div className="briefing-page min-h-screen">
        <main className="briefing-shell py-8" aria-busy="true" aria-label="Loading briefing">
          <div className="mb-4 flex items-center gap-2 text-xs text-[var(--text-secondary)]">
            <Loader2 className="h-4 w-4 animate-spin text-[var(--text-tertiary)]" aria-hidden />
            <span className="briefing-mono">Loading intelligence snapshot…</span>
          </div>
          <div className="briefing-card space-y-4 p-6">
            <Skeleton className="h-8 w-2/3 bg-white/10" />
            <Skeleton className="h-4 w-full bg-white/10" />
            <Skeleton className="h-4 w-5/6 bg-white/10" />
            <div className="grid gap-4 pt-4 md:grid-cols-[1.9fr_1.1fr]">
              <div className="space-y-3">
                <Skeleton className="h-40 w-full bg-white/10" />
                <Skeleton className="h-32 w-full bg-white/10" />
              </div>
              <div className="space-y-3">
                <Skeleton className="h-28 w-full bg-white/10" />
                <Skeleton className="h-24 w-full bg-white/10" />
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (showError) {
    return (
      <div className="briefing-page min-h-screen">
        <main className="briefing-shell py-8">
          <div className="briefing-card space-y-4 p-6">
            <p className="text-sm text-[var(--text-secondary)]">{state.error}</p>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                onClick={() => {
                  markMeaningfulInteraction("briefing_run_analysis_click");
                  void meta.runAnalysis();
                }}
              >
                Run analysis
              </Button>
              <Button size="sm" variant="outline" onClick={() => meta.refresh()}>
                Retry connection
              </Button>
              <Button asChild size="sm" variant="ghost">
                <Link
                  to="/app/dashboard"
                  onClick={() => {
                    markMeaningfulInteraction("briefing_to_dashboard_click");
                  }}
                >
                  Open dashboard
                </Link>
              </Button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="briefing-page min-h-screen">
        <main className="briefing-shell py-8">
          <div className="briefing-card p-6">
            <p className="mb-3 text-sm text-[var(--text-secondary)]">
              No briefing data available yet. Run an analysis from the dashboard or start one here.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                onClick={() => {
                  markMeaningfulInteraction("briefing_run_analysis_click");
                  void meta.runAnalysis();
                }}
              >
                Run analysis
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link
                  to="/app/dashboard"
                  onClick={() => {
                    markMeaningfulInteraction("briefing_to_dashboard_click");
                  }}
                >
                  Open dashboard
                </Link>
              </Button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  const structuredData = {
    "@type": "Report",
    "@id": "https://digital-war-room.com/daily-briefing#report",
    name: SHARE_TITLE_DAILY_BRIEFING,
    url: "https://digital-war-room.com/daily-briefing",
    datePublished: data.generatedAt.toISOString().slice(0, 10),
    dateModified: data.generatedAt.toISOString().slice(0, 10),
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
        structuredData={structuredData}
      />
      <div className="briefing-page min-h-screen">
        <main className="briefing-shell py-4">
          <div className="mb-3 flex items-center justify-between">
            <Link
              to="/app/dashboard"
              className="inline-flex items-center gap-1 text-xs text-[var(--text-secondary)] hover:text-white"
              onClick={() => {
                markMeaningfulInteraction("briefing_to_dashboard_click");
              }}
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to dashboard
            </Link>
            <p className="classification-banner briefing-mono text-[10px]">UNCLASSIFIED // OPEN SOURCE</p>
          </div>

          <BriefingHeader
            threatLevel={data.threatLevel}
            escalationScore={data.escalationScore}
            lastUpdated={data.generatedAt}
            isLive={meta.isLive}
            onRefresh={meta.refresh}
            onShare={share}
            onExportPDF={async () => {
              dispatch({ type: "EXPORT_START" });
              try {
                await exportPdf(data);
              } finally {
                dispatch({ type: "EXPORT_COMPLETE" });
              }
            }}
          />

          <nav className="briefing-card mb-4 flex flex-wrap gap-1 p-2">
            {NAV_ITEMS.map((item) => (
              <a
                key={item.id}
                href={`#${item.id}`}
                className="briefing-mono rounded border border-transparent px-2 py-1 text-[11px] text-[var(--text-secondary)] hover:border-[var(--border-default)] hover:text-white"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <section id="briefing-summary">
            <section id="briefing-start-here" className="briefing-card mb-4 scroll-mt-20 p-4">
              <h2 className="briefing-display text-xl">Start here: Top 3 actions for next 24h</h2>
              <p className="mt-1 text-xs briefing-mono text-[var(--text-secondary)]">
                Mission-first path to reduce time-to-value and get from signal to decision quickly.
              </p>
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                {buildTopActions(data.escalationScore, data.keyFindings.length, data.chokepoints.length).map((action) => (
                  <a
                    key={action.id}
                    href={action.target}
                    onClick={() => {
                      markMeaningfulInteraction("briefing_top_action_click");
                    }}
                    className="rounded border border-[var(--border-default)] bg-[var(--bg-elevated)]/30 p-3 transition-colors hover:border-[var(--text-primary)]"
                  >
                    <p className="text-sm font-semibold text-[var(--text-primary)]">{action.title}</p>
                    <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{action.rationale}</p>
                    <p className="mt-2 briefing-mono text-[10px] uppercase tracking-wide text-[var(--text-tertiary)]">{action.cta}</p>
                  </a>
                ))}
              </div>
            </section>
            <BLUFSection summary={data.bluf} contributingAgents={["NEWS", "SIGINT", "FININT"]} threatLevel={data.threatLevel} />
          </section>

          <section id="briefing-infographic" className="briefing-card mb-4 scroll-mt-20 p-4">
            <h2 className="briefing-display text-xl">Daily infographic snapshot</h2>
            <p className="mt-1 text-xs text-[var(--text-secondary)] briefing-mono">
              Same visual snapshot as the daily briefing email when available from the latest analysis run.
            </p>
            {data.newsletterInfographicDataUri ? (
              <img
                src={data.newsletterInfographicDataUri}
                alt="Daily intelligence infographic snapshot"
                className="mt-3 w-full max-w-3xl rounded-md border border-[var(--border-default)]"
                width={1200}
                height={675}
                loading="lazy"
                decoding="async"
              />
            ) : (
              <p className="mt-3 text-sm text-[var(--text-secondary)]">
                No infographic attached to this briefing yet. It appears after the daily newsletter pipeline generates one for
                this theater.
              </p>
            )}
          </section>

          <div className="briefing-grid">
            <div className="space-y-4">
              <KeyFindings
                findings={data.keyFindings}
                expandedFindings={state.expandedFindings}
                onToggleFinding={(id) => {
                  markMeaningfulInteraction("briefing_finding_toggle");
                  dispatch({ type: "TOGGLE_FINDING", payload: id });
                }}
              />
              <ScenarioAssessment scenarios={data.scenarios} />
              <PredictiveOutlook outlook={data.predictiveOutlook} />
              <section id="briefing-global" className="briefing-card p-3">
                <h2 className="briefing-display text-2xl">Global Impact</h2>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  {data.globalImpactNote?.trim() ||
                    "Energy and shipping sensitivities remain linked to chokepoint pressure and escalation trajectory."}
                </p>
              </section>
            </div>

            <aside className="space-y-3">
              <AgentStatusPanel agents={data.agents} />
              <MarketSnapshot market={data.market} />
              <ChokepointStatus chokepoints={data.chokepoints} />
            </aside>
          </div>

          <div className="mt-4">
            <AgentDeepDives
              agents={data.agents}
              expandedAgents={state.expandedAgents}
              onToggleAgent={(agent) => dispatch({ type: "TOGGLE_AGENT", payload: agent })}
            />
          </div>

          <BriefingFooter generatedAt={data.generatedAt} version={data.version} />
        </main>
      </div>
    </>
  );
}

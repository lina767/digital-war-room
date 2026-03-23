import { Link } from "react-router-dom";
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

const NAV_ITEMS = [
  { id: "briefing-summary", label: "Summary" },
  { id: "briefing-developments", label: "Findings" },
  { id: "briefing-predictive", label: "Outlook" },
  { id: "briefing-global", label: "Global" },
  { id: "briefing-watch", label: "Things to Watch" },
  { id: "briefing-sources", label: "Deep Dives" },
];

export default function DailyBriefingPage() {
  const { state, dispatch, meta } = useBriefingData();
  const exportPdf = useBriefingExport();
  const data = state.data;
  const showLoading = !data && (meta.initialLoadPending || state.isLoading);
  const showError = !data && state.error && !showLoading;

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
              <Button size="sm" onClick={() => void meta.runAnalysis()}>
                Run analysis
              </Button>
              <Button size="sm" variant="outline" onClick={() => meta.refresh()}>
                Retry connection
              </Button>
              <Button asChild size="sm" variant="ghost">
                <Link to="/app/dashboard">Open dashboard</Link>
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
              <Button size="sm" onClick={() => void meta.runAnalysis()}>
                Run analysis
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link to="/app/dashboard">Open dashboard</Link>
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
            <Link to="/app/dashboard" className="inline-flex items-center gap-1 text-xs text-[var(--text-secondary)] hover:text-white">
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
            <BLUFSection summary={data.bluf} contributingAgents={["NEWS", "SIGINT", "FININT"]} threatLevel={data.threatLevel} />
          </section>

          <div className="briefing-grid">
            <div className="space-y-4">
              <KeyFindings
                findings={data.keyFindings}
                expandedFindings={state.expandedFindings}
                onToggleFinding={(id) => dispatch({ type: "TOGGLE_FINDING", payload: id })}
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

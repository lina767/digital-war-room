import { Link } from "react-router-dom";
import { ArrowLeft, Info } from "lucide-react";

const HowItWorks = () => {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-10">
        {/* Back link */}
        <div className="mb-6 sm:mb-8 flex items-center justify-between gap-3">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors touch-manipulation"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to dashboard</span>
          </Link>
          <div className="hidden sm:flex items-center gap-2 text-xs text-muted-foreground font-mono">
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-border">
              <Info className="h-3 w-3" />
            </span>
            <span>How Digital War Room works</span>
          </div>
        </div>

        {/* Title */}
        <header className="mb-8 sm:mb-10">
          <p className="font-mono text-[11px] sm:text-xs tracking-[0.28em] text-muted-foreground uppercase mb-3">
            DOCUMENTATION
          </p>
          <h1 className="text-2xl sm:text-3xl md:text-4xl font-semibold tracking-tight mb-3">
            How the Digital War Room works
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground max-w-3xl">
            The Digital War Room is an OSINT-based situational awareness platform. It aggregates open-source signals
            from multiple intelligence streams, computes an escalation score, and surfaces a concise BLUF-style briefing.
          </p>
        </header>

        <main className="space-y-10 sm:space-y-12">
          {/* Intelligence streams */}
          <section className="space-y-4">
            <h2 className="text-lg sm:text-xl font-semibold tracking-tight">Intelligence streams</h2>
            <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
              The platform combines several open-source intelligence (OSINT) streams. Each stream is handled by a
              dedicated agent that calls external APIs, normalises the results, and computes a stream-specific score.
            </p>
            <div className="grid gap-4 sm:gap-5 md:grid-cols-2">
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">FININT – Financial Intelligence</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>Brent / WTI oil prices and key market indicators</li>
                  <li>Polymarket prediction markets on US–Iran, Trump, military actions, China, trade, regime stability</li>
                  <li>Combined into a financial escalation score</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">SIGINT – Signals Intelligence</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>Military aircraft and naval movements (ADS-B / open feeds)</li>
                  <li>Conflict reports from think tanks and defence-focused outlets</li>
                  <li>Signals aggregated into a SIGINT escalation score</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">NEWS – Open-source media</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>News articles related to the selected conflict</li>
                  <li>Headline and body sentiment (escalatory vs. de-escalatory)</li>
                  <li>Summarised into a news_score for the supervisor</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">GEOINT – Geospatial Intelligence</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>Thermal anomaly detections (e.g. NASA FIRMS)</li>
                  <li>Hotspots and clusters in relevant regions</li>
                  <li>Geospatial anomaly score for the conflict</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">SOCMINT – Social Media Intelligence</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>Signals from Telegram, Reddit and RSS feeds</li>
                  <li>Focus on escalation-related narratives and spikes</li>
                  <li>Top social signals passed to the supervisor</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">TECHINT – Technical Intelligence</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>Tech &amp; export control news impacting escalation</li>
                  <li>Internet outage signals (IODA / Cloudflare / OONI)</li>
                  <li>Shodan activity around relevant regions</li>
                </ul>
              </div>
            </div>
          </section>

          {/* Analysis pipeline */}
          <section className="space-y-4">
            <h2 className="text-lg sm:text-xl font-semibold tracking-tight">Analysis pipeline</h2>
            <ol className="space-y-3 text-sm sm:text-[15px] text-muted-foreground max-w-3xl list-decimal list-inside">
              <li>
                <strong className="text-foreground">Select a conflict.</strong> In the dashboard header you choose a
                conflict (for example “US–Iran” or “Ukraine–Russia”). This value is passed to all agents.
              </li>
              <li>
                <strong className="text-foreground">Agents run in parallel.</strong> FININT, SIGINT, NEWS, GEOINT,
                SOCMINT and TECHINT run concurrently. Each agent:
                <ul className="mt-1.5 ml-5 space-y-1 list-disc list-inside">
                  <li>Calls its external APIs (oil, FIRMS, news, markets, etc.)</li>
                  <li>Handles timeouts and errors gracefully (returns empty/error objects instead of crashing)</li>
                  <li>Computes a stream-specific score and structured result</li>
                </ul>
              </li>
              <li>
                <strong className="text-foreground">Rule-based by default.</strong> By default, agents follow a fixed
                rule-based tool chain (no per-agent LLM calls), which keeps costs low and behaviour predictable.
              </li>
              <li>
                <strong className="text-foreground">Supervisor synthesis.</strong> Once all agent results are ready,
                they are fed into a supervisor model that produces a single JSON payload:
                <ul className="mt-1.5 ml-5 space-y-1 list-disc list-inside">
                  <li>
                    <code>escalation_score</code> (0–100) and <code>threat_level</code> (MINIMAL / LOW / ELEVATED / HIGH
                    / CRITICAL)
                  </li>
                  <li>
                    <code>key_findings</code>, <code>scenarios</code> and a short BLUF-style{" "}
                    <code>summary</code>
                  </li>
                </ul>
              </li>
              <li>
                <strong className="text-foreground">Background auto-runs.</strong> A background job periodically
                re-runs the analysis for the default conflict (by default every 6 hours). The latest result is cached
                and served instantly when you open the dashboard.
              </li>
            </ol>
          </section>

          {/* Dashboard features */}
          <section className="space-y-4">
            <h2 className="text-lg sm:text-xl font-semibold tracking-tight">Dashboard features</h2>
            <div className="grid gap-4 sm:gap-5 md:grid-cols-2">
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">Live ticker &amp; threat level</h3>
                <p className="text-xs sm:text-[13px] text-muted-foreground">
                  A live ticker at the top surfaces key headlines and signals from the latest analysis. The threat
                  level badge (e.g. ELEVATED / HIGH) gives an at-a-glance view of the current escalation assessment.
                </p>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">Agents panel</h3>
                <p className="text-xs sm:text-[13px] text-muted-foreground">
                  The left panel shows all intelligence agents, their full names and data sources. It explains what
                  feeds power FININT, SIGINT, NEWS, GEOINT, SOCMINT and TECHINT for the selected conflict.
                </p>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">Conflict map &amp; timeline</h3>
                <p className="text-xs sm:text-[13px] text-muted-foreground">
                  The central map visualises the conflict region and overlays relevant signals. At the bottom, an
                  escalation timeline highlights key time buckets across the day.
                </p>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">Intelligence feed</h3>
                <p className="text-xs sm:text-[13px] text-muted-foreground">
                  The right panel contains the daily briefing, latest headlines, an events timeline and additional
                  modules: a proximity analyzer (FIRMS vs. civilian infrastructure), connectivity signals and
                  prediction markets.
                </p>
              </div>
            </div>
          </section>

          {/* LLM modes & cost model */}
          <section className="space-y-4">
            <h2 className="text-lg sm:text-xl font-semibold tracking-tight">LLM modes &amp; cost model</h2>
            <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
              The platform is designed to stay useful even when LLM usage is heavily constrained. All agents can run
              purely rule-based. The supervisor can use a lightweight model (e.g. Claude Haiku or OpenAI gpt‑4o‑mini)
              or be disabled entirely in favour of a deterministic scoring scheme.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-1.5">
                <h3 className="font-mono text-xs tracking-wider text-primary">Default mode</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>Agents run rule-based (fixed tool chains, no per-agent LLM calls)</li>
                  <li>Supervisor uses a small model (Haiku / gpt‑4o‑mini) for synthesis</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-1.5">
                <h3 className="font-mono text-xs tracking-wider text-primary">Cost-saving options</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>Disable the Sonnet fallback when agents disagree</li>
                  <li>Switch the supervisor to OpenAI gpt‑4o‑mini for very low cost per run</li>
                  <li>Run a fully rule-based supervisor (no LLM at all)</li>
                </ul>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
};

export default HowItWorks;


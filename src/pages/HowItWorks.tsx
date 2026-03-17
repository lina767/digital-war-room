import { Link } from "react-router-dom";
import { Database, ClipboardList } from "lucide-react";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";

const HOW_IT_WORKS_DESCRIPTION =
  "The Digital War Room is an OSINT-based situational awareness platform. It aggregates open-source signals from multiple intelligence streams, computes an escalation score, and surfaces a concise BLUF-style briefing.";

const HOW_IT_WORKS_FAQ = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: [
    {
      "@type": "Question",
      name: "What is the Digital War Room?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "The Digital War Room is an OSINT-based situational awareness platform. It aggregates open-source signals from multiple intelligence streams (GEOINT, SIGINT, SOCMINT, FININT, TECHINT, and others), computes a composite escalation score, and surfaces a concise BLUF-style briefing.",
      },
    },
    {
      "@type": "Question",
      name: "What intelligence streams does the platform use?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "The platform uses 12 intelligence streams: SIGINT, Chokepoint, FININT, NEWS, SOCMINT, Proximity, GEOINT, TECHINT, CYBER, ENERGY, PROTEST, and DIPLO. Each stream is handled by a dedicated agent that calls external APIs and computes a stream-specific score.",
      },
    },
    {
      "@type": "Question",
      name: "Where can I see the data sources?",
      acceptedAnswer: {
        "@type": "Answer",
        text: "All data sources are listed in the Source Directory with reliability ratings. The Methodology page explains how the composite escalation score and threat levels are computed.",
      },
    },
  ],
};

const HowItWorks = () => {
  return (
    <>
      <SEO
        title="How It Works — Digital War Room"
        description={HOW_IT_WORKS_DESCRIPTION}
        path="/how-it-works"
        structuredData={HOW_IT_WORKS_FAQ}
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "How It Works", url: "https://digital-war-room.com/how-it-works" },
        ]}
      />
      <ContentPageLayout
      label="DOCUMENTATION"
      title="How the Digital War Room works"
      description={HOW_IT_WORKS_DESCRIPTION}
      maxWidth="5xl"
    >
      <div className="space-y-10 sm:space-y-12">
          {/* Intelligence streams */}
          <section className="space-y-4">
            <h2 className="text-lg sm:text-xl font-semibold tracking-tight">Intelligence streams</h2>
            <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
              The platform combines several open-source intelligence (OSINT) streams. Each stream is handled by a
              dedicated agent that calls external APIs, normalises the results, and computes a stream-specific score.
            </p>
            <p className="text-sm text-muted-foreground">
              <Link to="/sources" className="inline-flex items-center gap-1.5 text-primary hover:underline">
                <Database className="h-3.5 w-3.5" />
                <span>Source Directory</span>
              </Link>
              {" "}– transparent, searchable list of all data sources with reliability ratings.
            </p>
            <p className="text-sm text-muted-foreground">
              <Link to="/methodology" className="inline-flex items-center gap-1.5 text-primary hover:underline">
                <ClipboardList className="h-3.5 w-3.5" />
                <span>Methodology</span>
              </Link>
              {" "}– scoring weights, threat-level thresholds and Signal Framework (state vs. exile media).
            </p>
            <p className="text-xs sm:text-[13px] text-muted-foreground max-w-3xl">
              For conflict <strong className="text-foreground">Iran</strong>, keywords and synthesis explicitly include
              Hezbollah–IDF and Houthis (no separate dropdown). Global impact (e.g. oil price moves, Strait of Hormuz /
              chokepoint risk) is derived from ENERGY and surfaced in key findings and the dashboard Global Impact panel.
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
                  <li>Conflict reports from think tanks (Hezbollah, Houthis, Iran, Yemen, Lebanon in keywords for Iran)</li>
                  <li>Signals aggregated into a SIGINT escalation score</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">NEWS – Open-source media</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>News articles for the selected conflict (Iran query includes Hezbollah, Houthi, IDF, Yemen, Lebanon)</li>
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
                  <li>Signals from Telegram, Reddit and RSS (for Iran: includes Houthi, Hezbollah, IDF, Yemen, Lebanon)</li>
                  <li>Focus on escalation-related narratives and spikes</li>
                  <li>Top social signals passed to the supervisor</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">TECHINT – Technical Intelligence</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>Tech &amp; export control news impacting escalation</li>
                  <li>Internet outage signals (IODA v2 / Cloudflare / OONI)</li>
                  <li>Shodan activity around relevant regions</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">CYBER – Threat Intelligence</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>CISA KEV, threat reports, AlienVault OTX pulses</li>
                  <li>GreyNoise: malicious scanner context (7d)</li>
                  <li>Combined into a cyber escalation score</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">ENERGY – Commodities &amp; Gas</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>EU gas storage (AGSI+), Brent/WTI (Alpha Vantage)</li>
                  <li>For Iran: global impact note when oil moves significantly (Strait of Hormuz / chokepoint risk)</li>
                  <li>Energy score and commodities feed supervisor and Global Impact panel</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">PROTEST – Civil Society</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>ACLED protests/riots, GDELT protest coverage</li>
                  <li>Civil society unrest score for the supervisor</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">DIPLO – Diplomacy / Legal</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>OFAC SDN, EU sanctions, UN/ICJ press</li>
                  <li>Diplomatic and legal signals; feeds Sanctions Compliance risk score</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">PROXIMITY – Strike–Civilian</h3>
                <ul className="text-xs sm:text-[13px] text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>NASA FIRMS thermal anomalies vs. OSM schools/hospitals (and optional tunnel/military sites)</li>
                  <li>Human-shield / collateral risk labels; evidence list for key findings</li>
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
                conflict (currently &quot;Iran&quot;). This value is passed to all agents. For Iran, Hezbollah, Houthis and
                global impact (oil, Hormuz) are included in keywords and synthesis without a separate dropdown.
              </li>
              <li>
                <strong className="text-foreground">Agents run in parallel.</strong> FININT, SIGINT, NEWS, GEOINT,
                SOCMINT, TECHINT, CYBER, ENERGY, PROTEST, DIPLO and PROXIMITY run concurrently. Each agent:
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
                  The left panel shows all 11 intelligence agents (FININT, SIGINT, NEWS, GEOINT, SOCMINT, TECHINT,
                  CYBER, ENERGY, PROTEST, DIPLO, PROXIMITY), their full names and data sources for the selected conflict.
                </p>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">Conflict map &amp; timeline</h3>
                <p className="text-xs sm:text-[13px] text-muted-foreground">
                  The central map visualises the conflict region and overlays thermal anomalies, aircraft, ships and
                  optional layers: heatmap (ACLED), SAM rings, air routes, sea lanes (e.g. Strait of Hormuz). An
                  escalation timeline highlights key findings by category.
                </p>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">Intelligence feed &amp; Global Impact</h3>
                <p className="text-xs sm:text-[13px] text-muted-foreground">
                  The right panel contains the updated briefing, a <strong className="text-foreground">Global Impact</strong> panel
                  (when available: oil/Hormuz risk for Iran from ENERGY and key findings), latest headlines, events
                  timeline, proximity analyzer (FIRMS vs. civilian infrastructure), connectivity signals and
                  prediction markets.
                </p>
              </div>
              <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
                <h3 className="font-mono text-xs tracking-wider text-primary">Sanctions Compliance</h3>
                <p className="text-xs sm:text-[13px] text-muted-foreground">
                  OFAC SDN and EU sanctions (from DIPLO), geofencing (SIGINT ships/aircraft vs sanctions zones),
                  AIS anomaly detection (spoofing, dark activity), and a compliance risk score (LOW/MEDIUM/HIGH/CRITICAL).
                  Conflict-level sanctions awareness (e.g. Iran) elevates risk. On-demand sanctions search for firms/partners.
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
      </div>
    </ContentPageLayout>
    </>
  );
};

export default HowItWorks;


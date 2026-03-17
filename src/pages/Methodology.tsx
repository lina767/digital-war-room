import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";
import { TITLE_METHODOLOGY, DESCRIPTION_METHODOLOGY } from "@/lib/seoCopy";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

const AGENT_WEIGHTS = [
  { name: "SIGINT", weight: 12, fullName: "Signals Intelligence" },
  { name: "CHOKEPOINT", weight: 11, fullName: "Maritime Chokepoint Monitor" },
  { name: "FININT", weight: 9, fullName: "Financial Intelligence" },
  { name: "NEWS", weight: 9, fullName: "News / OSINT" },
  { name: "SOCMINT", weight: 9, fullName: "Social Media Intelligence" },
  { name: "PROXIMITY", weight: 9, fullName: "Strike–Civilian / Human-Shield" },
  { name: "GEOINT", weight: 7, fullName: "Geospatial Intelligence" },
  { name: "TECHINT", weight: 7, fullName: "Technical Intelligence" },
  { name: "CYBER", weight: 7, fullName: "Threat Intelligence" },
  { name: "ENERGY", weight: 7, fullName: "Energy / Commodities" },
  { name: "PROTEST", weight: 7, fullName: "Civil Society / Protest" },
  { name: "DIPLO", weight: 6, fullName: "Diplomacy / Legal" },
] as const;

const THREAT_LEVELS = [
  { level: "CRITICAL", min: 80, description: "Severe escalation; immediate attention" },
  { level: "HIGH", min: 60, description: "Elevated risk; significant indicators" },
  { level: "ELEVATED", min: 40, description: "Moderate escalation" },
  { level: "LOW", min: 20, description: "Low activity" },
  { level: "MINIMAL", min: 0, description: "Baseline; no significant signals" },
];

const CHART_COLORS = [
  "hsl(var(--primary))",
  "hsl(var(--primary) / 0.9)",
  "hsl(var(--primary) / 0.8)",
  "hsl(var(--primary) / 0.7)",
  "hsl(var(--primary) / 0.6)",
  "hsl(var(--primary) / 0.55)",
  "hsl(var(--muted-foreground) / 0.8)",
  "hsl(var(--muted-foreground) / 0.7)",
  "hsl(var(--muted-foreground) / 0.6)",
  "hsl(var(--muted-foreground) / 0.5)",
  "hsl(var(--muted-foreground) / 0.45)",
  "hsl(var(--muted-foreground) / 0.4)",
  "hsl(var(--muted-foreground) / 0.35)",
];

const Methodology = () => {
  return (
    <>
      <SEO
        title={TITLE_METHODOLOGY}
        description={DESCRIPTION_METHODOLOGY}
        path="/methodology"
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Methodology", url: "https://digital-war-room.com/methodology" },
        ]}
      />
      <ContentPageLayout
        label="METHODOLOGY"
        title="Scoring methodology"
        description={DESCRIPTION_METHODOLOGY}
        maxWidth="5xl"
      >
      <div className="space-y-10 sm:space-y-12">
        {/* Composite scoring */}
        <section className="space-y-4">
          <h2 className="text-lg sm:text-xl font-semibold tracking-tight">
            Composite scoring
          </h2>
          <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
            The escalation score (0–100) is a weighted sum of each agent’s score. Weights reflect the relative importance of each stream for situational awareness. SIGINT and Chokepoint carry the highest weights because military movements and maritime chokepoints are strong leading indicators.
          </p>
          <div className="rounded-lg border border-border bg-card/40 p-4 sm:p-5 space-y-4">
            <div className="space-y-2">
              <p className="text-xs font-medium text-foreground/90">Formal definition</p>
              <p className="text-xs text-muted-foreground">
                Let n = 12 agents; s<sub>i</sub> ∈ [0, 100] the score of agent i; w<sub>i</sub> the weight with ∑<sub>i=1</sub><sup>n</sup> w<sub>i</sub> = 1. Then the composite score is:
              </p>
              <pre className="font-mono text-xs text-muted-foreground bg-muted/50 rounded px-3 py-2 overflow-x-auto">
                S = ∑<sub>i=1</sub><sup>n</sup> w<sub>i</sub> s<sub>i</sub>  ∈  [0, 100]
              </pre>
              <p className="text-xs text-muted-foreground">
                The weights w<sub>i</sub> are given in the table and chart below.
              </p>
            </div>
            <p className="font-mono text-xs text-muted-foreground">
              combined_score = Σ (agent_score × weight) with Σ weight = 100%
            </p>
            <div className="h-64 sm:h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={AGENT_WEIGHTS}
                  layout="vertical"
                  margin={{ top: 4, right: 8, left: 4, bottom: 4 }}
                >
                  <XAxis type="number" domain={[0, 14]} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number) => [`${value}%`, "Weight"]}
                    labelFormatter={(_, payload) => payload[0]?.payload?.fullName ?? ""}
                    contentStyle={{ fontSize: 12 }}
                  />
                  <Bar dataKey="weight" radius={[0, 4, 4, 0]} maxBarSize={28}>
                    {AGENT_WEIGHTS.map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="mt-4 w-full text-xs sm:text-[13px] text-muted-foreground border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 font-medium text-foreground">Agent</th>
                  <th className="text-right py-2 font-medium text-foreground">Weight</th>
                </tr>
              </thead>
              <tbody>
                {AGENT_WEIGHTS.map((a) => (
                  <tr key={a.name} className="border-b border-border/60">
                    <td className="py-1.5 font-mono">{a.name}</td>
                    <td className="py-1.5 text-right">{a.weight}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Threat level thresholds */}
        <section className="space-y-4">
          <h2 className="text-lg sm:text-xl font-semibold tracking-tight">
            Threat level thresholds
          </h2>
          <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
            The composite score is mapped to a single threat level used in the dashboard and briefing. When the supervisor LLM is used, it can override this with its own assessment; otherwise the rule-based thresholds below apply.
          </p>
          <div className="rounded-lg border border-border bg-card/40 p-4 max-w-2xl">
            <p className="text-xs font-medium text-foreground/90 mb-2">Decision rule L(S)</p>
            <p className="text-xs text-muted-foreground mb-3">
              Threat level as a function of composite score S:
            </p>
            <ul className="font-mono text-xs text-muted-foreground space-y-1.5">
              <li>L(S) = CRITICAL  ⇔  S ≥ 80</li>
              <li>L(S) = HIGH      ⇔  60 ≤ S &lt; 80</li>
              <li>L(S) = ELEVATED  ⇔  40 ≤ S &lt; 60</li>
              <li>L(S) = LOW       ⇔  20 ≤ S &lt; 40</li>
              <li>L(S) = MINIMAL  ⇔  S &lt; 20</li>
            </ul>
          </div>
          <ul className="space-y-2 text-sm text-muted-foreground max-w-2xl">
            {THREAT_LEVELS.map((t) => (
              <li key={t.level} className="flex items-baseline gap-2">
                <span className="font-mono font-medium text-foreground min-w-[4.5rem]">
                  {t.level}
                </span>
                <span className="text-muted-foreground/80">score ≥ {t.min}</span>
                <span className="text-muted-foreground/70">– {t.description}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* Peak-weighted escalation */}
        <section className="space-y-4">
          <h2 className="text-lg sm:text-xl font-semibold tracking-tight">
            Peak-weighted escalation (predictive block)
          </h2>
          <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
            For the predictive block and escalation forecast, a peak-weighted score is used so that the top three agent scores have more influence. This avoids a single quiet stream (e.g. no protest events) from dampening the overall escalation signal when other streams are spiking.
          </p>
          <div className="rounded-lg border border-border bg-card/40 p-4 max-w-3xl space-y-3">
            <p className="text-xs font-medium text-foreground/90">Formal definition</p>
            <p className="text-xs text-muted-foreground">
              Let s<sub>(1)</sub> ≥ s<sub>(2)</sub> ≥ … ≥ s<sub>(n)</sub> be the agent scores sorted in descending order. Define:
            </p>
            <ul className="font-mono text-xs text-muted-foreground space-y-1.5 list-none pl-0">
              <li>s̄<sub>top3</sub> = (1/3)(s<sub>(1)</sub> + s<sub>(2)</sub> + s<sub>(3)</sub>)  — average of top 3 scores</li>
              <li>S<sub>peak</sub> = 0.6 · s̄<sub>top3</sub> + 0.4 · S  — peak-weighted combination</li>
              <li>S<sub>esc</sub> = max(S, S<sub>peak</sub>)  — escalation score used in the predictive block</li>
            </ul>
            <p className="text-xs text-muted-foreground">
              Thus the displayed escalation score never drops below the composite S; when the top three streams are high, S<sub>esc</sub> increases.
            </p>
          </div>
        </section>

        {/* Signal Framework methodology */}
        <section className="space-y-4">
          <h2 className="text-lg sm:text-xl font-semibold tracking-tight">
            Signal Framework methodology
          </h2>
          <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
            The <strong className="text-foreground">Signal Framework</strong> (narrative agent) compares state-aligned and exile/independent media for the Iran conflict. It does not produce a numeric escalation score; instead it yields a synthesis probability, a source comparison table, and latency/credibility gaps.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
              <h3 className="font-mono text-xs tracking-wider text-primary">
                State-aligned sources
              </h3>
              <p className="text-xs sm:text-[13px] text-muted-foreground">
                IRNA, Fars News, Tasnim, Press TV (RSS). These are compared for narrative framing, timing and lexical choices.
              </p>
            </div>
            <div className="rounded-lg border border-border bg-card/40 p-4 space-y-2">
              <h3 className="font-mono text-xs tracking-wider text-primary">
                Exile / independent sources
              </h3>
              <p className="text-xs sm:text-[13px] text-muted-foreground">
                Iran International, Radio Farda, BBC Persian. The agent detects information vacuums, reaction latency and credibility gaps between the two sides.
              </p>
            </div>
          </div>
          <p className="text-xs sm:text-[13px] text-muted-foreground max-w-3xl">
            The methodology is documented in the backend (<code className="text-foreground/80">signal_framework_agent</code>). Outputs include <code className="text-foreground/80">synthesis_text</code>, <code className="text-foreground/80">synthesis_probability</code>, <code className="text-foreground/80">source_comparison_table</code> and <code className="text-foreground/80">signal_assessment</code> (latency, credibility gaps). These feed the supervisor and the dashboard Narrative / Signal Framework panel.
          </p>
          <p className="text-xs sm:text-[13px] text-muted-foreground max-w-3xl">
            <strong className="text-foreground/90">Synthesis:</strong> The narrative agent uses qualitative signals (Lexical, Latency, Discrepancy, Reaction) and produces a probabilistic synthesis from the state-vs.-exile comparison (Bayesian-style in the backend). For full formulas and logic see <code className="text-foreground/80">signal_framework_agent</code>.
          </p>
        </section>

        {/* Further rule-based logic */}
        <section className="space-y-4">
          <h2 className="text-lg sm:text-xl font-semibold tracking-tight">
            Further rule-based scores
          </h2>
          <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
            <strong className="text-foreground/90">Per-agent scores (0–100)</strong> are computed per stream, either by rule-based logic or LLM-assisted aggregation. Details are in the backend agents (e.g. TECHINT: base score plus increments for export-news volume, IODA outages, OONI blocks, Shodan exposure; CYBER: KEV, threat reports, GreyNoise context).
          </p>
          <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
            <strong className="text-foreground/90">Compliance risk</strong> (see <code className="text-foreground/80">backend/compliance/risk_score</code>) maps a numeric score (0–100) to an ordinal level: LOW (score &lt; 25), MEDIUM (25 ≤ score &lt; 50), HIGH (50 ≤ score &lt; 75), CRITICAL (score ≥ 75). Inputs include sanctions matches, geofencing alerts, supply-chain and AIS anomalies, and escalation context.
          </p>
        </section>
      </div>
    </ContentPageLayout>
    </>
  );
};

export default Methodology;

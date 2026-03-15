import { ContentPageLayout } from "@/components/ContentPageLayout";
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
    <ContentPageLayout
      label="METHODOLOGY"
      title="Scoring methodology"
      description="How the composite escalation score and threat level are computed from 12 intelligence streams, and how the Signal Framework compares state vs. exile media."
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
          <div className="rounded-lg border border-border bg-card/40 p-4 sm:p-5">
            <p className="font-mono text-xs text-muted-foreground mb-3">
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
            For the predictive block and escalation forecast, a peak-weighted score is used so that the top three agent scores have more influence. This avoids a single quiet stream (e.g. no protest events) from dampening the overall escalation signal when other streams are spiking. The formula combines the average of the top three scores (60%) with the composite score (40%), then takes the maximum of that and the raw composite.
          </p>
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
        </section>
      </div>
    </ContentPageLayout>
  );
};

export default Methodology;

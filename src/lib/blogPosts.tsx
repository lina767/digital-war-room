import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { DOCS_HOW_IT_WORKS, DOCS_METHODOLOGY, DOCS_SOURCE_DIRECTORY } from "@/lib/docLinks";

/**
 * Blog posts for the Digital War Room. Add entries here or later replace with CMS/API.
 */

export type BlogSeries = "weekly-insights";

export const BLOG_SERIES_LABELS: Record<BlogSeries, string> = {
  "weekly-insights": "Weekly insights",
};

export interface BlogPost {
  slug: string;
  title: string;
  date: string; // ISO date (YYYY-MM-DD)
  excerpt: string;
  body: ReactNode;
  /** Shown as a small label on listing and post (e.g. Weekly insights). */
  series?: BlogSeries;
}

export const BLOG_POSTS: BlogPost[] = [
  {
    slug: "weekly-briefing-2026-04-08",
    series: "weekly-insights",
    title: "Weekly Briefing: Ceasefire Window, Cyber Signals, and Market Risk",
    date: "2026-04-08",
    excerpt:
      "A weekly readout on the Islamabad ceasefire window, anomalous cyber indicators in Iran and Yemen, and the 48-hour watchlist for potential escalation.",
    body: (
      <>
        <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mt-2">
          Infographic: Summary of the Newsletter
        </h2>
        <img
          alt="Infographic detailing signals of the week, including a diplomatic pivot in Islamabad, two major unknowns regarding Iran's botnet infrastructure and Yemen's ICS."
          src="https://resend-attachments.s3.amazonaws.com/9b42655d-cd66-4bcd-8a1a-b155488734dc"
          className="w-full max-w-3xl rounded-md border border-border"
          width={1200}
          height={630}
          loading="lazy"
          decoding="async"
        />

        <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mt-6">
          Signals of the Week
        </h2>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Social channels remain saturated with war content, keeping SOCMINT as the loudest
          signal. GEOINT remains the most volatile and operationally useful stream, swinging
          sharply between quiet and strike-heavy days. CYBER has moved up materially, including
          a jump to 78 and elevated hostile scanning pressure against Iranian infrastructure.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Diplomatic momentum shifted on this cycle: a Pakistan-mediated bilateral off-ramp
          replaced UNSC-centered stalemate, and a two-week ceasefire was announced with talks
          scheduled in Islamabad on Friday, April 10. The negotiation frame reportedly centers
          on Iran's 10-point proposal, including sanctions relief, release of frozen assets,
          and changes to regional force posture.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          One key ambiguity remains unresolved: Pakistan's public framing suggested broader
          coverage including Lebanon, while Israeli messaging contested that scope. That
          contradiction is a likely early stress point if the ceasefire weakens.
        </p>

        <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mt-6">
          The 2 Biggest Unknowns
        </h2>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          During a kinetic pause, the highest-information signals often come from infrastructure
          preparation rather than rhetoric. Two anomalous cyber patterns now carry outsized
          predictive value.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          What is Iran building with its botnet infrastructure?
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Iran's malicious outbound-to-inbound traffic profile is a clear outlier in this
          dataset, indicating sustained offensive preparation rather than passive defense.
          Outbound activity is concentrated in router-targeting exploitation, including
          high-volume attempts against known NETGEAR and D-Link vulnerabilities associated with
          remote code execution.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The operational interpretation is pre-positioning: building distributed access on
          internet edge devices to support later DDoS capacity, proxy infrastructure, or
          deniable escalation options. Under a ceasefire, this activity can continue while
          remaining outside narrow kinetic terms.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Framed against ongoing talks, the core unknown is strategic intent: what capability
          Iran aims to have ready when the two-week window closes.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          Who is targeting Yemen's ICS/SCADA systems, and why now?
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Yemen is the only theater zone in this cycle showing elevated ICS/SCADA-oriented
          activity. Signals include reconnaissance patterns associated with industrial control
          environments and credential pressure against VPN exposure that could provide pathways
          into operational technology networks.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          In practical terms, this profile can map to early-stage preparation against physical
          infrastructure: ports, desalination, power generation, and logistics nodes. The
          actor and timeline remain uncertain, but the distinctiveness of the signal makes it a
          top-priority watch item.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The ceasefire context increases urgency because geographic scope remains contested and
          gray-zone cyber actions can be framed as outside overt kinetic violations.
        </p>

        <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mt-6">What's Next?</h2>
        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          The Islamabad Talks Are the New Hinge
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Friday's Islamabad meeting is now the central decision point. The key indicator is
          not meeting occurrence but concrete movement on sanctions, frozen assets, and force
          posture terms. Without progress on at least one track, ceasefire durability remains
          structurally weak.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          Base Case: Narrow Compliance, Quiet Capability-Building
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The most likely near-term pattern is visible restraint in kinetic channels while
          cyber, proxy, and preparatory activity continues in areas not explicitly covered by
          the agreement. In that regime, infrastructure and cyber telemetry remain the most
          reliable intent signals.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          Tail Risk: Collapse Before Day 14
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Primary failure triggers include negotiation breakdown, sanction shocks during talks,
          or a non-deniable strike event. A second pathway is gray-zone escalation through
          cyber or infrastructure disruption where attribution remains contested.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">Market Reaction</h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Oil repriced sharply lower on ceasefire headlines, compressing geopolitical premium
          but not eliminating it. This implies markets are treating de-escalation as the base
          case while still pricing meaningful reversal risk if talks stall or violation signals
          emerge.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">48-Hour Watchlist</h3>
        <ul className="list-disc pl-5 text-sm sm:text-[15px] text-muted-foreground space-y-1.5 mb-4 max-w-3xl">
          <li>AIS confirmation that Hormuz tanker transit actually normalizes.</li>
          <li>Whether the Lebanon scope contradiction resolves or worsens.</li>
          <li>Residual proxy/IRGC fire after initial command-filter lag.</li>
          <li>Pre-meeting Islamabad signaling on sanctions or asset release language.</li>
          <li>Acceleration in Iran botnet build-out and Yemen ICS reconnaissance.</li>
          <li>Oil futures response during Asian open sessions.</li>
        </ul>

        <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mt-6">
          Shipped This Week and Why It Matters
        </h2>
        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          Dashboard Chat MVP
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          A first conversational interface is now embedded directly in the dashboard, allowing
          users to query the intelligence layer in natural language.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          Caching and Layered Intelligence
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Pipeline execution now uses layered caching to reduce recomputation, lower latency,
          and improve cost efficiency while preserving historical context.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          Agents and Fetchers
        </h3>
        <ul className="list-disc pl-5 text-sm sm:text-[15px] text-muted-foreground space-y-1.5 mb-4 max-w-3xl">
          <li>PROTEST agent removed and replaced with zero-weight stub behavior.</li>
          <li>GEOINT tuned for GDELT DOC timeline and FIRMS baseline handling.</li>
          <li>FININT weighting updated with chokepoint/AISStream alignment.</li>
          <li>NEWS pipeline added optional Guardian API path.</li>
          <li>SOCMINT prioritization adjusted for WarMonitor3 relevance.</li>
          <li>Cross-agent corroboration and degraded-feed grammar improvements.</li>
        </ul>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">Pizza Index</h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
          The header now includes a Pizza Index marker as a light OSINT meta-signal for
          potential crisis tempo shifts near major command centers.
        </p>
      </>
    ),
  },
  {
    slug: "weekly-insights-auto-generated-summaries",
    series: "weekly-insights",
    title: "Weekly insights: auto-generated analysis summaries",
    date: "2026-03-21",
    excerpt:
      "What “weekly insights” means here: synthesized readouts from the multi-agent analysis pipeline, not editorial opinion.",
    body: (
      <>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          <strong className="text-foreground font-medium">Weekly insights</strong> are short,
          auto-generated summaries derived from the same analysis stack that powers the
          dashboard: FININT, SIGINT, GEOINT, news, cyber, energy, and related streams fused
          by the supervisor into escalation scores, key findings, scenarios, and compliance
          context. They reflect what the pipeline measured in a given window – not a separate
          editorial column.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          On the live app, the closest surface is the{" "}
          <span className="text-foreground/90">Updated Briefing</span> and related panels after
          each run: recap, key findings, predictive outlook, and sanctions/compliance blocks are
          all synthesized from agent outputs. When we publish weekly insight notes on this blog,
          they condense or highlight patterns from that process for readers who want the gist
          without opening the full dashboard.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          For a daily email version of the briefing for a chosen conflict, see the{" "}
          <Link to="/newsletter" className="text-primary hover:underline">
            Daily Briefing newsletter
          </Link>
          . The blog’s weekly line is complementary: longer-horizon or thematic summaries
          rather than every daily delta.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
          Technical background:{" "}
          <Link to={DOCS_HOW_IT_WORKS} className="text-primary hover:underline">
            How it works
          </Link>
          ,{" "}
          <Link to={DOCS_METHODOLOGY} className="text-primary hover:underline">
            Methodology
          </Link>
          , and{" "}
          <Link to={DOCS_SOURCE_DIRECTORY} className="text-primary hover:underline">
            Source Directory
          </Link>
          .
        </p>
      </>
    ),
  },
  {
    slug: "welcome-to-the-blog",
    title: "Welcome to the Digital War Room Blog",
    date: "2025-03-17",
    excerpt:
      "Updates, methodology notes, weekly insights, and context on how we build and run the platform.",
    body: (
      <>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          This blog hosts short updates on the platform: new data sources, methodology
          changes,{" "}
          <Link
            to="/blog/weekly-insights-auto-generated-summaries"
            className="text-primary hover:underline"
          >
            weekly insights
          </Link>{" "}
          (auto-generated analysis summaries), and occasional notes on conflict monitoring and
          OSINT. No fluff – just what matters for understanding how the Digital War Room works
          and what it can do.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
          For a full overview of the system, see{" "}
          <Link to={DOCS_HOW_IT_WORKS} className="text-primary hover:underline">How it works</Link>
          {" "}and the{" "}
          <Link to={DOCS_METHODOLOGY} className="text-primary hover:underline">Methodology</Link>
          {" "}page, and the{" "}
          <Link to={DOCS_SOURCE_DIRECTORY} className="text-primary hover:underline">Source Directory</Link>
          {" "}for sources and reliability ratings.
        </p>
      </>
    ),
  },
];

/** Get post by slug, or undefined if not found. */
export function getPostBySlug(slug: string): BlogPost | undefined {
  return BLOG_POSTS.find((p) => p.slug === slug);
}

/** All slugs for static routes / sitemap. */
export function getAllSlugs(): string[] {
  return BLOG_POSTS.map((p) => p.slug);
}

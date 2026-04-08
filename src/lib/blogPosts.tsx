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

        <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mt-6">Signals of the Week</h2>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Social media channels (Telegram, X, Reddit) remain saturated with war content, making
          SOCMINT consistently the loudest signal. GEOINT is the most volatile and actionable,
          swinging from 20 on quiet days to 100 on active strike days, which makes it the best
          real-time indicator of kinetic escalation. CYBER is rising: yesterday&apos;s jump to 78,
          from a stable level around 56, alongside GreyNoise data showing 44K+ malicious IPs
          targeting Iranian infrastructure, suggests pre-positioning that is unlikely to pause
          with the ceasefire, since cyber operations remain the most deniable escalation tool
          available during the negotiating window. Diplomacy had been stalling through early this
          week, with UN vetoes and international condemnation signals converging. That picture
          flipped today: Pakistan opened a bilateral off-ramp bypassing the UNSC entirely, and a
          two-week ceasefire was announced, with negotiations set to continue in Islamabad on
          Friday, April 10. The framework on the table is Iran&apos;s 10-point proposal, delivered via
          Pakistan and accepted by the US as a workable basis for negotiations, which reportedly
          requires the lifting of all sanctions and UN resolutions against Iran, along with the
          release of frozen Iranian assets. One ambiguity to watch: Pakistan&apos;s PM stated that the
          ceasefire extends to Lebanon, while Netanyahu&apos;s office explicitly denied that Lebanon is
          covered, which is a contradiction that is likely to be where the ceasefire frays first,
          if it frays at all.
        </p>

        <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mt-6">The 2 Biggest Unknown</h2>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Amid the noise of escalating kinetic and cyber activity across the platform, two signals
          in the dataset stand out as genuinely anomalous, patterns that cannot yet be explained
          by known operations or public reporting.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Under the two-week ceasefire announced today, both signals move up the priority stack
          rather than down. Kinetic instruments are frozen, and diplomatic rhetoric is
          de-escalating, which means the loud signals in the dataset have temporarily lost
          informational value. The quiet signals, such as infrastructure pre-positioning and
          industrial control reconnaissance, become the actual proxy for intent, because they are
          the only signals an actor cannot fake for the sake of negotiations. What each side
          builds, maps, and pre-positions during the pause is the clearest available read on what
          they plan to do when the pause ends.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          What is Iran building with its botnet infrastructure?
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Before unpacking the signal, a note on terminology: a botnet is a network of
          internet-connected devices (often home routers, IP cameras, or other poorly secured
          Internet of Things (IoT) hardware) that have been silently infected with malware and can
          be remotely controlled by an attacker. Once assembled, a botnet can be used to flood
          websites with traffic (a DDoS attack, or distributed denial-of-service), to route
          malicious activity through innocent-looking IP addresses, or to serve as pre-positioned
          infrastructure for a larger operation. The devices&apos; real owners typically have no idea
          their router is part of one.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          With that in mind, Iran&apos;s profile is the single most anomalous signal in the entire
          dataset. its outbound-to-inbound malicious traffic ratio sits at 20.27 percent, meaning
          that for every five probes scanning Iran from the outside, Iran is sending one attack of
          its own. The contrast with every other actor in the theater is stark: the United States
          sits at 2.02 percent (a predominantly defensive posture, mostly absorbing inbound scans),
          Lebanon at 0.93 percent, and Israel at 0.68 percent. Iran is the clear outlier, and the
          shape of its outbound activity is as telling as the volume.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The outbound traffic is dominated by active exploitation of specific software
          vulnerabilities, known in the industry as CVEs, short for Common Vulnerabilities and
          Exposures, the standardized catalog of publicly disclosed security flaws. Two stand out:
          CVE-2024-12847, which allows command execution on NETGEAR routers (3,084 hits), and a
          D-Link HNAP remote code execution flaw (2,316 hits). Remote code execution, or RCE,
          means an attacker can run their own commands on a victim device from anywhere in the
          world, effectively taking it over. Both are router exploits, and routers are the classic
          raw material of botnet construction: always online, rarely patched, and sitting directly
          on the open internet.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          What we are watching, then, is not reconnaissance. It is active asset preparation. Iran
          methodically hijacks routers in third countries to build out a distributed network that
          it can later weaponize for DDoS operations, proxy routing, or pre-positioning ahead of a
          larger cyber campaign. The unknown is not whether Iran is building something, but what it
          is building it for, and against whom.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The ceasefire sharpens rather than softens this question. Iran&apos;s 10-point proposal on
          the table in Islamabad includes maximalist demands: sanctions relief, the release of
          frozen assets, and US force withdrawal from regional bases. If those demands are not met,
          Iran needs a credible post-ceasefire threat that does not require openly breaking the
          agreement, and a distributed, pre-positioned botnet targeting US or Gulf infrastructure
          is exactly that kind of threat: deniable, scalable, and activatable on short notice. The
          two-week window also gives Iran more operational room to continue the build-out, not
          less, because defensive attention across the theater will relax while diplomacy is the
          headline story and attribution pressure eases. The botnet question should now be read as
          a question about what Iran wants to be holding on April 21, when the window expires. The
          CYBER jump to 78 and the 20.27 percent outbound ratio are best understood together as Iran
          constructing its post-ceasefire option space.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          Who is targeting Yemen&apos;s ICS/ SCADA systems, and why now?
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Yemen is the only theater zone triggering high-priority alerts against ICS/SCADA
          infrastructure. The acronyms are worth unpacking: ICS stands for Industrial Control
          Systems, and SCADA for Supervisory Control and Data Acquisition. Together, they describe
          the specialized computer systems that run physical infrastructure, which is the software
          and hardware controlling power plants, water treatment facilities, port cranes,
          pipelines, and manufacturing lines. Unlike ordinary IT systems, ICS/SCADA networks
          directly touch the physical world, which means an intrusion can translate into real-world
          disruption: a blackout, a contaminated water supply, a halted port.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Two signatures stand out in the Yemen data. The first is the Tridium Niagara AX Fox ICS
          Scanner, with 1,844 inbound hits flagged as critical infrastructure reconnaissance.
          Niagara is a widely deployed framework for managing building and industrial systems, and
          scanning for it is a classic prelude to targeting physical infrastructure. The second is
          an active Fortinet SSL VPN brute-forcer operating outbound from Yemeni space.
          Brute-forcing means automated password-guessing at scale, and VPNs are the typical entry
          point to internal industrial networks. Someone, almost certainly a state actor, is
          systematically mapping Yemen&apos;s industrial control surface, and this signal appears
          nowhere else in the theater.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Given the Houthis&apos; dimension of the conflict, the implications are serious. ICS mapping
          of this kind is typically a precursor to operations targeting physical infrastructure,
          such as port facilities, desalination plants, or power generation facilities. The
          uniqueness of the signal suggests Yemen has entered an operational phase that the other
          theater countries have not, and that a hybrid kinetic-cyber strike against Yemeni
          physical infrastructure may be closer than public reporting indicates. The unknown is the
          actor and the timeline.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The ceasefire makes this signal more urgent for three reasons. First, the geographic
          scope of the agreement is contested, while Pakistan&apos;s PM says it covers Lebanon and
          elsewhere, Netanyahu&apos;s office denies Lebanon is included, and no party explicitly
          mentions Yemen. A cyber operation against Yemeni port facilities, desalination, or power
          generation could plausibly proceed without being framed as a ceasefire violation, which
          means the deterrent against it has weakened rather than strengthened. Second, ICS
          reconnaissance has a characteristic lead time of weeks to months before any disruption
          event. That timeline now runs through the negotiating window and out the other side, and
          the operation may well be designed to be ready precisely when the ceasefire expires or
          collapses. Third, a ceasefire shifts the conflict&apos;s center of gravity toward secondary
          theaters, because that is where plausible deniability is highest and where the
          agreement&apos;s terms are vaguest. Yemen was already the theater with the most anomalous ICS
          signal in the dataset; it is now also the theater in which a hybrid kinetic-cyber event
          would create the clearest violation narrative. Those two facts compound, placing Yemen
          ICS activity near the top of the 48-hour watchlist in the new situation.
        </p>

        <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mt-6">What&apos;s Next?</h2>
        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          The Islamabad Talks Are the New Hinge
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Everything now pivots on Friday, April 10, when US and Iranian delegations meet in
          Islamabad under Pakistani mediation. The two-week ceasefire is the frame, but the
          substance is Iran&apos;s 10-point proposal, which the US has accepted as a workable basis for
          negotiations without committing to any specific term. The gap between &quot;workable
          basis&quot; and &quot;definitive agreement&quot; is where the next two weeks will be decided, and
          the signal to watch is not whether the talks happen but whether they produce concrete
          movement on the three maximalist demands at the core of the Iranian proposal: sanctions
          relief, release of frozen Iranian assets, and withdrawal of US combat forces from
          regional bases. Anything short of visible progress on at least one of those tracks leaves
          the ceasefire structurally fragile, regardless of the public tone from Islamabad.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          Base Case: Narrow Compliance, Quiet Capability-Building
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The most probable path is a holding pattern in which the kinetic phase stays frozen,
          diplomatic theater dominates the headlines, and the actual strategic activity moves
          underground. This is consistent with Iran&apos;s historical pattern in negotiated frameworks.
          Across the JCPOA period, the 2023 prisoner-swap arrangement, and multiple rounds of
          nuclear talks, Iran&apos;s approach has not been to break agreements outright but to comply
          with their narrow terms while accelerating activity outside their scope. The current
          agreement is narrow: it covers kinetic operations and Hormuz transit, nothing else.
          Expect Iran to meet the visible terms (Hormuz reopening is already being coordinated),
          while using the two-week window to continue cyber pre-positioning, proxy capability
          transfers, and infrastructure reconnaissance that do not technically violate the deal. The
          botnet build-out and the Yemen ICS signal are the leading indicators of this pattern in
          the current dataset.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The symmetry matters: the US and Israel are using the same window for intelligence
          collection, force repositioning, and covert action planning that the ceasefire does not
          cover. Netanyahu&apos;s denial that Lebanon is included is the most visible example. Every
          major party is treating the two-week window as a tactical pause that preserves
          capability, not a genuine off-ramp. The correct analytical question is not whether any
          party will cheat, but which activities fall outside the agreement&apos;s scope and which ones
          are accelerating.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          Tail Risk: Ceasefire Collapse Before Day 14
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The triggers have shifted from kinetic to negotiation-failure: a walkout from Islamabad,
          withdrawal of the 10-point proposal, a US move to expand sanctions during the window, or
          a confirmed Israeli strike on Iran that cannot be treated as deniable. A second tail risk
          is a hybrid gray-zone event neither side can cleanly attribute, such as a cyber incident
          against Gulf or US infrastructure, or an ICS-enabled disruption in Yemen. The Yemen
          signal in the dataset is the single clearest candidate for this kind of event.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">Market Reaction</h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Markets priced the ceasefire as a structural shift, not a relief rally. Brent fell
          roughly 13 percent to about $95 a barrel, which is the biggest one-day drop in oil prices
          since the 1991 Gulf War, and WTI fell about 14 percent to roughly $96. The geopolitical
          risk premium compressed from about $14 per barrel to $4-6, which is the more important
          number than the headline percentage move because it tells you what markets think the
          ceasefire is actually worth. The residual premium implies traders are pricing in
          meaningful collapse risk but treating the base case as durable de-escalation, and Brent
          at $95 is still well above the $73 mark right before the war began at the end of
          February, which shows that most of the war premium has unwound, but not all.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The asymmetry of the model is reversal risk. If the Islamabad talks stall or a violation
          incident occurs, the $4-6 residual premium can rebuild to $14+ within hours. A plausible
          range on a talks-collapse headline is Brent +8 to +15 percent intraday, with a sharper
          move if the trigger is a specific incident rather than a diplomatic breakdown. The
          longer-horizon 15-20 percent Gulf transit disruption scenario is no longer the base case.
          However, it remains the stress-test anchor, and the EIA&apos;s latest outlook still forecasts
          Brent peaking at $115 in Q2 2026 before easing. Institutional forecasters are not yet
          treating the ceasefire as a structural inflection.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The operational tool to watch is Hormuz AIS data. The ceasefire is explicitly conditioned
          on reopening the strait, and Trump has said the US will help with the traffic buildup. If
          transits resume within 24 to 48 hours, the ceasefire is behaving as advertised. If they
          do not, that is the earliest concrete signal the agreement is not holding, well before
          any political announcement would confirm it, and well before oil prices would fully
          reprice it.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">48-Hour Watchlist</h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          In descending order of importance: AIS data on whether tanker traffic through the Strait
          of Hormuz actually resumes, as the first operational test of whether the ceasefire is
          real or rhetorical; the Lebanon question, specifically whether the Pakistan/Netanyahu
          contradiction resolves or produces an incident; residual IRGC or proxy fire past the
          24-hour command-filter lag window; pre-meeting signaling from Islamabad, particularly
          leaked language on sanctions relief or asset release; continued CYBER activity, with
          attention to whether the Iranian botnet build-out and Yemen ICS scanning accelerate during
          the ceasefire (acceleration during a pause is a stronger signal of intent than the same
          activity during open conflict); and oil futures behavior in the Asian open.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The meta-question is whether the ceasefire is a genuine off-ramp or a tactical pause in
          which both sides reposition for a second phase. The answer will not come from the
          Islamabad press conferences. It will come from the AIS data, the infrastructure signals,
          and the cyber pillar, because those are the only channels where neither side has an
          incentive to perform de-escalation it does not actually intend. The answer will be
          visible in the data well before it reaches the headlines.
        </p>

        <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mt-6">
          Shipped this week &amp; why it matters?
        </h2>
        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">Dashboard Chat MVP</h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          A conversational interface now lives directly on the dashboard, letting you query the
          platform&apos;s intelligence in natural language rather than hunting through panels and
          filters. It is explicitly an early-stage MVP, but the direction matters: it turns the
          dashboard from a read-only surface into something you can interrogate. Ask a question,
          get an answer grounded in the same multi-agent pipeline that powers the rest of the
          product. Over time, this becomes the fastest path from raw signal to actionable insight,
          especially for users who do not want to learn the dashboard&apos;s full layout before getting
          value out of it.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">
          Caching and Layered Intelligence
        </h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          Behind the scenes, the data pipeline now operates in layers with caching between them, so
          repeated queries and recurring agent calls no longer trigger full recomputation from
          source. The practical effect is lower latency, lower API costs, and a more responsive
          dashboard. But the deeper payoff is architectural: a layered model makes it possible to
          distinguish fresh intelligence from persistent context, which is the foundation for any
          serious briefing or historical comparison feature down the line.
        </p>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">Agents and Fetchers</h3>
        <ul className="list-disc pl-5 text-sm sm:text-[15px] text-muted-foreground space-y-1.5 mb-4 max-w-3xl">
          <li>PROTEST agent removed and replaced with a stub / zero weight; protest references stripped from UI/docs.</li>
          <li>GEOINT: GDELT DOC timeline tuning, FIRMS baseline in Postgres, parallel fetches.</li>
          <li>FININT: Polymarket weighting; chokepoint/AISStream docs and client alignment.</li>
          <li>NEWS: optional Guardian API.</li>
          <li>SOCMINT: WarMonitor3 prioritization.</li>
          <li>CEO / signal-framework: cross-agent corroboration, degraded feed grammar, war-relevant signal priority.</li>
        </ul>

        <h3 className="text-lg sm:text-xl font-semibold tracking-tight mt-5">Pizza Index</h3>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          The header now shows a Pizza Index: the long-running OSINT joke-turned-indicator that
          tracks late-night pizza delivery activity near the Pentagon as a proxy for crisis
          response. It is a half-serious signal, half cultural marker, and it belongs on a
          dashboard like this.
        </p>

        <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mt-6">
          How useful was this week&apos;s briefing?
        </h2>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">Write me a message!</p>
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

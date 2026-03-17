# Reddit — Post Templates

## 1. Show & Tell (r/SideProject, r/opensource, r/Python)

### Post Title
`I'm a political science student and I built an AI-powered OSINT platform with 11 intelligence agents — architecture, trade-offs, and what I learned`

### Post Body

```
## What I built (and why a polisci student built it)

I study political science at LMU Munich and I'm writing my thesis on semiconductor industrial policy. My research sits at the intersection of tech policy, international law, and geopolitics.

While researching Iran, I kept running into the same problem: the data exists (flight tracking, satellite imagery, sanctions databases, social media, oil futures) but nobody is fusing it. So I built a platform that does.

An AI-powered OSINT conflict monitoring platform: 11 specialized AI agents run in parallel (Digital War Room), each tapping into different public data sources — an LLM supervisor synthesizes everything into a single threat assessment.

**Current focus:** Iran and the Middle East.

## The agents

| Agent | What it monitors | Data sources |
|-------|-----------------|--------------|
| FININT | Oil prices, prediction markets, sanctions | Brent/WTI, Polymarket, OFAC |
| SIGINT | Military aircraft, intel reports, Hormuz tankers | ADS-B (adsb.fi), Conflict RSS, Chokepoint AISStream |
| NEWS | Media sentiment and coverage | NewsAPI, GDELT, RSS |
| GEOINT | Satellite thermal anomalies | NASA FIRMS, ACLED |
| SOCMINT | Social media signals | Telegram, Reddit, RSS |
| TECHINT | Internet disruptions, censorship | IODA, OONI, Shodan |
| CYBER | Threat intel, exploits | CISA KEV, OTX, GreyNoise |
| ENERGY | Gas storage, commodity prices | AGSI+, Alpha Vantage |
| PROTEST | Protests and riots | ACLED, GDELT |
| DIPLO | Sanctions, UN/ICJ activity | OFAC SDN, EU list, UN RSS |
| PROXIMITY | Strike-civilian correlation | NASA FIRMS + OpenStreetMap |

## Architecture decisions

**No agent frameworks.** I tried LangGraph early on and found the abstraction cost too high for my use case. Each agent is a plain Python function (`run_*_agent(conflict: str) -> Dict`). Orchestration is `ThreadPoolExecutor` with 12 workers and 75-second timeouts. If one API times out, the system continues with degraded data.

**Dual-mode agents.** Every agent supports LLM tool-calling (Claude Haiku drives tool selection) and rule-based execution (fixed tool chain, no LLM). Controlled by one env var. If the LLM fails mid-run, it falls back to rule-based automatically.

**LLM abstraction.** Swap between Anthropic and OpenAI with one env var. No framework lock-in. The provider-agnostic layer is ~30 lines of code.

## Trade-offs and honest assessment

**What works well:**
- Parallel execution + fallbacks = reliable. The system has never fully crashed even with multiple API outages.
- Rule-based mode is fast and deterministic. Good for testing and cost control.
- 20+ public APIs give surprisingly comprehensive coverage.

**What doesn't work well (yet):**
- Score calibration is hard. The weighted composite score (SIGINT 13%, FININT 10%, etc.) is hand-tuned, not empirically validated.
- The Proximity agent depends on Overpass API rate limits. Heavy use gets 429'd.
- Narrative analysis (state vs. exile media) is interesting but hard to validate — who decides what's "true"?

**What I'd do differently:**
- Start with fewer agents (3-4) and add complexity gradually.
- Build evaluation metrics earlier. Hard to improve what you can't measure.
- Consider async from the start instead of threading. The mix of sync agents and async HTTP calls is awkward.
- Learn more software engineering fundamentals before diving in (I'm a polisci student, not a CS major — I learned a lot the hard way).

## Tech stack

- **Backend:** Python 3, FastAPI, httpx (async HTTP)
- **LLM:** Anthropic Claude (Sonnet for supervisor, Haiku for agents) or OpenAI
- **Frontend:** React, TypeScript, Vite, Tailwind, shadcn/ui
- **Observability:** OpenTelemetry → Jaeger

## What's next

- Better score calibration (backtesting against historical events)
- More conflicts beyond Iran
- Public demo / open-source release (TBD)

Happy to answer questions about the architecture, the OSINT sources, or the agent design. What would you have done differently?
```

### Subreddit-specific adjustments

- **r/Python:** Focus on the ThreadPoolExecutor pattern, dual-mode agents, and the LLM abstraction. Less geopolitics, more code.
- **r/opensource:** Emphasize the open data sources and the value of public APIs. Discuss licensing considerations.
- **r/SideProject:** Include your motivation, timeline, and personal journey. More story, less code.

---

## 2. Geopolitical Analysis (r/geopolitics)

### Post Title
`Patterns in Iranian military posture — what open-source data reveals`

### Post Body Template

```
## Context

[1-2 paragraphs setting up the geopolitical question. No product mentions. Pure analysis.]

Example: "Over the past [timeframe], several indicators suggest [thesis about Iranian military/political behavior]. This post examines publicly available data across multiple domains — military movements, satellite imagery, financial markets, and media analysis — to assess [specific question]."

## Methodology

[Brief, honest description of your data sources. Name the sources, not the tool.]

Example: "This analysis draws on ADS-B flight tracking data (adsb.fi), NASA FIRMS thermal anomaly data (VIIRS instrument), ACLED conflict event data, NewsAPI coverage volume, and OFAC sanctions records. Social media signals from Telegram and Reddit complement the structured data."

## Findings

### Military movements
[What ADS-B and maritime tracking data shows. Specific aircraft types, patterns, comparisons to baseline.]

### Satellite indicators
[NASA FIRMS findings. Number of anomalies, FRP values, geographic distribution.]

### Financial and market signals
[Oil price movements, prediction market probabilities, sanctions activity.]

### Information landscape
[News coverage patterns, social media signals, state vs. independent media divergence if relevant.]

## Assessment

[2-3 paragraphs synthesizing the findings into a coherent assessment. State your confidence level. Acknowledge what the data can't tell you.]

## Limitations

[Honest about what open-source data misses. "ADS-B data only shows aircraft with transponders on. Military aircraft can and do fly without them." etc.]

---

**Sources:** [list of data sources used — adsb.fi, NASA FIRMS, ACLED, etc.]
```

### Rules for r/geopolitics

1. **Never mention your tool by name.** Reference your methodology ("I analyzed ADS-B data") not your product.
2. **No links to your project.** If someone asks in the comments, you can briefly describe it.
3. **Academic tone.** r/geopolitics expects sourced, analytical posts. No hot takes.
4. **Flair:** Use "Analysis" or the default flair. Don't use "News" for analysis posts.
5. **Engage genuinely in comments.** Answer questions with data, not promotion.

---

## 3. Technical Discussion (r/MachineLearning, r/LocalLLaMA, r/gis)

### Post Title Template
`[Question/Discussion] [specific technical topic] — [your context]`

Example: `[D] Multi-agent orchestration: ThreadPoolExecutor vs async vs frameworks — experiences from building an 11-agent OSINT system`

### Post Body Template

```
## Context

I'm building a system that runs [N] AI agents in parallel, each hitting [description of workload]. I went with [approach] and want to discuss the trade-offs.

## My approach

[2-3 paragraphs describing what you did and why]

## What I'm unsure about

[Genuine questions — not rhetorical. You're asking because you want to learn.]

1. [Specific question]
2. [Specific question]
3. [Specific question]

## What I've tried

[Brief summary of alternatives you considered and why you chose your current approach]

Has anyone dealt with similar patterns? What worked for you?
```

### Key principle

These posts should be **genuinely asking for input**, not disguised self-promotion. If you're not actually uncertain about something, don't pretend to be. Share your experience and ask where you might be wrong.

---

## Reddit General Tips

1. **Comment-to-post ratio:** Comment helpfully on 5-10 threads before making your own post. Build karma and recognition organically.
2. **Respect subreddit rules.** Read the sidebar before posting. r/geopolitics in particular has strict rules about sourcing and tone.
3. **Don't cross-post the same content.** Adapt for each subreddit's audience.
4. **Respond to every comment** on your posts. Reddit rewards engagement.
5. **Upvote generously.** Be a good community member.
6. **Never argue.** If someone disagrees, respond with data or acknowledge their point. Reddit memory is long.

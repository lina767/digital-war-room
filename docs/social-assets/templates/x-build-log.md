# X (Twitter) — Build Log Template

## Single Tweet Format

```
[What you built/shipped today — one sentence]

[Why it matters — one sentence]

[Screenshot or diagram]
```

**Length:** Under 280 chars for the text. Attach an image.
**Frequency:** 3-5x per week. Consistency beats virality.

---

## Template: Feature Ship

```
Shipped: [feature name]

[What it does in plain language — 15 words max]

The interesting part: [one technical or design insight]

[screenshot/diagram]
```

---

## Template: Problem → Solution

```
Problem: [what broke or was hard]
Solution: [what you did]
Result: [metric or outcome]

[screenshot if applicable]
```

---

## Template: Architecture Insight

```
TIL while building my OSINT platform:

[Insight in 1-2 sentences]

The code is stupidly simple:
[4-6 lines of code as image or inline]
```

---

## FIRST POST — Ready to Publish

```
I study political science. I build intelligence tools.

11 AI agents monitoring Iran in parallel: military aircraft, naval vessels, NASA satellites, oil futures, sanctions lists, social media, internet outages, civil unrest events, media narratives.

No agent framework. Just Python's ThreadPoolExecutor with 75s timeouts.

If an API fails? The system keeps running with degraded data. If the LLM fails? Deterministic rules take over.

The boring architecture decisions are the ones that survive production.

[attach architecture diagram or dashboard screenshot]
```

---

## SECOND POST — Proximity Agent

```
Built an agent that correlates strike locations with civilian infrastructure.

NASA FIRMS thermal data + OpenStreetMap schools/hospitals via Overpass API.

Strike < 50m from a school? CRITICAL_PROXIMITY.
Strike < 150m + nearby military site? PROBABLE_HUMAN_SHIELD.

As someone who studies international law, this is the agent that matters most to me.

[attach screenshot of EvidenceCard]
```

---

## THIRD POST — Policy Meets Code

```
The gap that frustrates me as a political science student:

Policy analysts understand the problem. Engineers understand the tools. Almost nobody does both.

So I built a system where:
- SIGINT knowledge (which aircraft patterns matter) comes from policy expertise
- The orchestration (parallel agents, timeouts, fallbacks) is pure engineering

Neither side alone produces useful intelligence.

The best OSINT tools will be built by people who understand the domain, not just the code.
```

---

## FOURTH POST — Dual-Mode Pattern

```
Every AI agent in my OSINT platform has two modes:

1. LLM mode: Claude Haiku picks which tools to call
2. Rule-based mode: fixed tool chain, no LLM at all

Switch between them with one env var.

If the LLM fails mid-run? Automatic fallback to rule-based.

The result: an AI system that works without AI.

That's not a bug. That's the architecture.
```

---

## Tips for X

1. **No hashtags in tweets** (unlike LinkedIn). They look spammy on X. Exception: #BuildInPublic is acceptable.
2. **Post between 8-10 AM and 6-8 PM** (US timezone) for maximum reach.
3. **Quote-tweet** relevant OSINT/AI posts with your take (1-2 sentences). This is your primary growth lever.
4. **Images/screenshots get 2-3x engagement.** Always attach something visual.
5. **Pin your best thread** (the OSINT thread or architecture overview).
6. **Reply to replies.** The algorithm rewards conversations.

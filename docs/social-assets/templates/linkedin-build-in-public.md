# LinkedIn — Build in Public Template

## Post Structure (recommended)

```
[Hook — one provocative statement or question]

[2-3 paragraphs: context, decision, outcome]

[Lesson learned or takeaway]

[Call to discussion — question to the audience]

#hashtags (3-5 max)
```

**Length:** 1,200–1,800 characters (LinkedIn cuts off at ~210 chars; front-load the hook).
**Format:** No bullet-point walls. Short paragraphs (2-3 sentences each). One idea per post.
**Images:** Architecture diagram or screenshot. LinkedIn posts with images get 2x engagement.

---

## Template: Architecture Decision

```
I ditched [popular framework] and built [component] with [simpler approach].

Here's why:

[Problem you faced — 2 sentences]

[What the popular approach does and why it didn't work for you — 2-3 sentences]

[What you built instead and the result — 2-3 sentences]

The counterintuitive lesson: [one sentence takeaway]

What's your experience with [framework/approach]? Have you gone simpler and been happier?

#OSINT #AIEngineering #BuildInPublic #MultiAgentSystems #Geopolitics
```

---

## Template: Lessons Learned

```
[Number] things I learned building [component/feature]:

1. [Lesson] — [one sentence explanation]
2. [Lesson] — [one sentence explanation]
3. [Lesson] — [one sentence explanation]

The one that surprised me most: [expand on one lesson, 2-3 sentences]

Building in public means sharing the ugly parts too.

What's a hard lesson you learned recently?

#BuildInPublic #OSINT #AI
```

---

## FIRST POST — Ready to Publish

### "Why a political scientist built a multi-agent intelligence system — without any agent framework"

```
I study political science. I research semiconductor policy and international law.

And somehow I ended up building a multi-agent AI system that monitors Iran using 11 intelligence agents in parallel.

Here's the thing: when you study geopolitics deeply enough, you realize the analysis tools don't match the complexity of what you're analyzing. You're reading IAEA reports, checking ADS-B flight data, scanning ACLED conflict events, watching oil futures — but you're doing it all manually, in separate tabs, hoping your brain catches the pattern.

So I built an AI-powered OSINT conflict monitoring platform — the Digital War Room. 11 specialized agents — FININT (financial markets), SIGINT (military aircraft and ships), NEWS, GEOINT (NASA satellite thermal data), SOCMINT (social media), TECHINT (internet disruptions), CYBER, ENERGY, CIVIL_UNREST, DIPLO (sanctions), and PROXIMITY (strike-civilian correlation). They run in parallel, each hitting 2-5 APIs with 75-second timeouts and automatic fallbacks. An LLM supervisor synthesizes everything into a single threat assessment.

Everyone told me to use LangGraph or CrewAI. I didn't. When your SIGINT agent has 75 seconds to query ADS-B endpoints (and any of them might timeout) — you need explicit control, not a framework deciding your execution order.

The result: 11 agents, 20+ public APIs, one composite threat score. The system runs every 6 hours automatically and has never fully crashed.

The lesson that surprised me most: understanding the problem domain matters more than engineering experience. Knowing which OSINT sources to combine — and which contradictions to flag — is the hard part. The code is just Python's ThreadPoolExecutor.

What tools do you wish existed for your field of research?

#OSINT #BuildInPublic #AIEngineering #Geopolitics #Iran
```

---

## SECOND POST IDEA — Geopolitical Analysis angle

### "How AI is changing intelligence gathering on Iran — and where it still fails"

```
Traditional intelligence analysis on Iran requires teams of specialists monitoring separate channels: military movements, financial markets, satellite imagery, social media, sanctions databases.

I built a system that does all of this simultaneously. As a political science student writing about semiconductor policy and tech export controls, I kept running into the same problem: the data exists, but no one is fusing it.

11 AI agents monitor Iran in parallel: SIGINT tracks military aircraft and naval vessels via ADS-B data. GEOINT watches NASA thermal anomalies. FININT monitors oil prices and prediction markets. TECHINT detects internet shutdowns — a classic pre-crackdown signal in Iran. DIPLO scans OFAC and EU sanctions lists. PROXIMITY correlates strike locations with schools and hospitals.

An LLM supervisor synthesizes all 11 streams into a unified assessment: escalation score, threat level, key findings, and probabilistic scenarios.

What makes this interesting from a policy perspective: it's not just data aggregation. The system flags when state media narratives (IRNA, Fars) diverge from exile media (Iran International, Radio Farda). It cross-references SIGINT military posture with FININT market signals. It detects contradictions that a single-source analyst would miss.

The democratization angle is real: all data sources are public or semi-public APIs. What used to require classified access is increasingly available through open-source intelligence and AI.

But here's where it still fails: AI is excellent at pattern detection and terrible at political judgment. It can tell you that three surveillance drones are orbiting the Persian Gulf — it can't tell you whether that's routine or pre-strike posture. That requires the kind of contextual understanding that comes from studying the region, not from training data.

The hard part isn't the data. It's knowing what to ignore.

#OSINT #Iran #Geopolitics #AIIntelligence #TechPolicy
```

---

## Tips for LinkedIn

1. **Post between 8-10 AM** (your audience's timezone, likely CET/EST).
2. **Reply to every comment** in the first 2 hours — LinkedIn rewards early engagement.
3. **Don't include links in the post body.** LinkedIn suppresses link posts. Put the link in the first comment.
4. **Use line breaks generously.** Mobile readers need whitespace.
5. **Tag 1-2 relevant people** only if you genuinely want their perspective (not for reach hacking).

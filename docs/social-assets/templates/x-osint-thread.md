# X (Twitter) — OSINT Thread Template (8-Tweet Structure)

Use this template when a live geopolitical event happens and you want to analyze it with the real-time Iran conflict OSINT tracker (Digital War Room) in real time. The goal: show the tool in action, provide genuine analysis, and demonstrate multi-source intelligence fusion.

---

## Structure: 8-Tweet Thread

### Tweet 1 — Hook + Context

```
[Event] just happened.

I ran it through 11 intelligence agents — SIGINT, GEOINT, FININT, NEWS, SOCMINT, TECHINT, CYBER, ENERGY, CIVIL_UNREST, DIPLO, PROXIMITY.

All open-source data. Here's what they found:
```

**Goal:** Establish relevance and credibility. State the event. Promise analysis, not hype. Your polisci background gives you authority here — the analysis should reflect domain expertise, not just tool output.

---

### Tweet 2 — SIGINT (Military Movements)

```
SIGINT: What's flying and sailing?

[ADS-B data finding — e.g., "3 RC-135 Rivet Joint surveillance aircraft over the Persian Gulf in the last 12 hours. 2 KC-135 tankers orbiting near [location]. This is [normal/elevated/unusual] compared to baseline."]

[Optional: screenshot of ADS-B data or map overlay]
```

**Source reference:** "via adsb.fi open data"

---

### Tweet 3 — NEWS + SOCMINT (Information Landscape)

```
NEWS: Media coverage pattern:

[Finding — e.g., "NewsAPI returns 47 articles in the last 24 hours. Sentiment: 60% ESCALATORY. Top sources: Reuters, Al Jazeera, BBC Persian."]

SOCMINT: Telegram/social signals:

[Finding — e.g., "Telegram channels reporting [X]. Reddit r/iran discussion volume up 3x."]
```

---

### Tweet 4 — GEOINT (Satellite / Ground Truth)

```
GEOINT: Satellite thermal data:

[Finding — e.g., "NASA FIRMS detected 12 thermal anomalies in [region] over the last 48 hours. FRP values suggest [military activity / industrial / wildfire]."]

[Finding from ACLED or conflict hotspot news if relevant]
```

---

### Tweet 5 — FININT + ENERGY (Market Reaction)

```
FININT: How are markets reading this?

[Finding — e.g., "Brent crude +2.3% in the last 6 hours. Polymarket 'Iran conflict escalation' contract at 34% (up from 28%)."]

ENERGY: EU gas storage at [X]%. [Interpretation of energy supply chain stress.]
```

---

### Tweet 6 — TECHINT + CYBER (Digital Signals)

```
TECHINT: Internet and digital infrastructure:

[Finding — e.g., "IODA detects no internet outages in Iran (positive signal — shutdowns often precede crackdowns). OONI confirms Telegram/Signal still blocked."]

CYBER: [GreyNoise/CISA KEV finding if relevant — e.g., "Malicious scanning targeting [country] infrastructure up 15% this week."]
```

---

### Tweet 7 — DIPLO + CIVIL_UNREST + PROXIMITY (Context)

```
DIPLO: [Sanctions or UN/ICJ finding — e.g., "OFAC SDN has 847 Iran-related entries. No new designations in the last 48 hours."]

CIVIL_UNREST: [ACLED finding — e.g., "ACLED reports 5 civil unrest events in [region] this week."]

PROXIMITY: [If relevant — e.g., "2 thermal anomalies within 150m of schools. Risk flag: HIGH_RISK."]
```

---

### Tweet 8 — Synthesis + Takeaway

```
Synthesis from all 11 streams:

Composite escalation score: [X]/100 — [THREAT_LEVEL]

Key takeaway: [1-2 sentences summarizing the overall assessment — e.g., "Military posture elevated but not at pre-strike levels. Markets pricing in risk premium. Social signals suggest anticipation, not panic."]

All data from public sources. This is what open-source intelligence looks like in 2026.
```

---

## Guidelines

1. **Only do this for real events.** Don't manufacture threads for engagement. The analysis must be genuine.
2. **Timestamp your data.** "Last 24 hours" or "as of [time] UTC" — OSINT has a shelf life.
3. **State uncertainty.** "This suggests X" not "This proves X." "Elevated compared to baseline" not "This means war."
4. **Credit your sources.** "via adsb.fi", "ACLED data", "NASA FIRMS VIIRS_SNPP_NRT." This builds trust.
5. **Don't oversell the tool.** The thread should provide analysis that stands on its own. The tool is the method, not the message.
6. **Screenshots matter.** Attach maps, dashboard views, or data tables. Visual evidence > text claims.
7. **End with an invitation.** "What are you seeing from your sources?" — this opens dialogue and builds community.

---

## Preparation Checklist

Before publishing an OSINT thread:

- [ ] Run a fresh analysis (`/api/analyze/refresh` or wait for periodic run)
- [ ] Review all 11 agent outputs for accuracy
- [ ] Remove any data that could be personally identifying
- [ ] Take 3-5 screenshots (sanitized — no API keys, no internal URLs)
- [ ] Draft all 8 tweets before posting the first one
- [ ] Check: does the analysis hold up without the tool? If yes, publish.

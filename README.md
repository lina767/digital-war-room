# Digital War Room

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Live Demo](https://img.shields.io/badge/demo-digital--war--room.com-0ea5e9)](https://digital-war-room.com) [![GitHub](https://img.shields.io/badge/GitHub-lina767%2Fdigital--war--room-181717?logo=github)](https://github.com/lina767/digital-war-room)

**AI-powered OSINT intelligence platform** — a multi-agent system that monitors global conflicts in near–real time across 11 intelligence disciplines (GEOINT, SIGINT, SOCMINT, FININT, TECHINT, CYBER, ENERGY, NEWS, PROTEST, DIPLO, PROXIMITY). One LLM supervisor synthesizes all streams into a single threat assessment with escalation scores, BLUF-style key findings, scenarios, and built-in sanctions compliance checks.

**Live demo:** [digital-war-room.com](https://digital-war-room.com) · **Code:** [github.com/lina767/digital-war-room](https://github.com/lina767/digital-war-room)

---

## What It Is & Why It Matters

Digital War Room aggregates open-source signals from 20+ public and semi-public APIs, runs 11 specialized agents in parallel, and fuses their outputs with a single supervisor LLM (Claude or GPT-4o). You get near–real-time escalation scores, key findings, predictive outlooks, and a compliance layer (geofencing, AIS anomaly detection, OFAC/EU cross-referencing) — all from one dashboard. No classified data; the platform shows what’s achievable with OSINT and AI orchestration.

**Current focus:** Iran / Middle East.

## Who It's For

- **OSINT analysts and researchers** — Multi-source fusion and BLUF-style briefings
- **Geopolitical risk consultants** — Escalation scores and scenario framing
- **Intelligence professionals** — AI-augmented workflows and compliance screening
- **AI/ML engineers** — Multi-agent architecture, direct LLM SDKs, graceful degradation

---

## Architecture

The backend runs **11 agents** via `ThreadPoolExecutor` (75s timeout per agent). Each returns a structured payload; the supervisor LLM fuses them into one assessment. The frontend is a React dashboard with threat level, key findings, agent cards, and map overlays.

### The 11 Intelligence Agents

| Agent | Sources | What It Measures |
|-------|---------|------------------|
| **FININT** | Brent/WTI/Gold, Polymarket, Metaculus, OFAC, Etherscan | Financial stress and market-implied conflict probability |
| **SIGINT** | ADS-B (adsb.fi, adsb.lol), CriticalThreats RSS, Hormuz Tankers (AISStream) | Military aircraft, intel reports, Hormuz tanker traffic |
| **NEWS** | NewsAPI, GDELT Doc API, RSS (BBC, DW, Al Jazeera, RFE/RL) | Open-source media sentiment and coverage volume |
| **GEOINT** | NASA FIRMS (thermal), ACLED, Sentinel Hub EO Browser | Satellite-detected thermal anomalies and conflict events |
| **SOCMINT** | Telegram, Nitter/X, Reddit, RSS, ReliefWeb | Social signal detection and grassroots sentiment |
| **TECHINT** | IODA, OONI, Shodan, Cloudflare Radar, Wayback Machine | Internet disruptions, censorship, cyber exposure |
| **CYBER** | CISA KEV, Mandiant/CrowdStrike RSS, AlienVault OTX, GreyNoise | Active exploits, threat intel, malicious scanning |
| **ENERGY** | AGSI+ (EU gas storage), Alpha Vantage (Brent/WTI) | Energy supply stress and commodity price shocks |
| **PROTEST** | ACLED (protests/riots), GDELT (protest coverage) | Civil society unrest and protest intensity |
| **DIPLO** | OFAC SDN, EU Consolidated List, UN Press, ICJ RSS | Diplomatic/legal signals, sanctions activity |
| **PROXIMITY** | NASA FIRMS + OSM (Overpass API) | Strike-to-civilian-infrastructure correlation, human-shield flags |

For a full diagram and design decisions, see **[Architecture & one-pager](docs/social-assets/one-pager.md)** and **[Architecture](docs/ARCHITECTURE.md)**.

### Data Sources (Summary)

| Category | Sources |
|----------|---------|
| **Conflict & events** | ACLED, GDELT |
| **Internet & censorship** | OONI, IODA, Shodan, Cloudflare Radar |
| **Markets & prediction** | Polymarket, Metaculus, Alpha Vantage, FRED, EIA |
| **Aircraft & vessels** | ADS-B Exchange (adsb.fi, adsb.lol), AISStream (Hormuz chokepoint) |
| **Threat intel** | GreyNoise, CISA KEV, AlienVault OTX |
| **Satellite & geography** | NASA FIRMS, Sentinel Hub, OpenStreetMap (Overpass) |
| **News & social** | NewsAPI, RSS, ReliefWeb, Telegram, Reddit |
| **Sanctions & legal** | OFAC SDN, EU Consolidated List, UN, ICJ |

Full API keys and setup: **[API keys & env](docs/API-KEYS.md)**.

---

## Screenshots

| Theater Map | Daily Briefing | Predictive Outlook |
|-------------|----------------|---------------------|
| Dashboard with conflict map, agent cards, and escalation score | BLUF-style key findings and scenario summaries | 24h forecast and risk indicators |
| *Screenshot: [docs/social-assets/](docs/social-assets/) or run the app and open `/`* | *Screenshot: `/daily-briefing`* | *Screenshot: predictive block on dashboard* |

*(Add actual screenshots or GIFs to `docs/social-assets/` and link them here for best discovery.)*

---

## Getting Started

```sh
# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend runs on `http://localhost:8080` by default. The backend is in `backend/` (Python, FastAPI). See **[Deployment](docs/DEPLOYMENT.md)** for running the backend locally or deploying frontend and backend.

### Environment Variables

In the project root `.env`:

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | Backend API URL (e.g. Railway); **required** for production |

All backend env vars and optional API keys per agent: **[API keys & env](docs/API-KEYS.md)**.

### Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start dev server |
| `npm run build` | Production build |
| `npm run preview` | Preview production build |
| `npm run lint` | Run ESLint |
| `npm run test` | Run tests |

---

## Documentation

- **[Deployment](docs/DEPLOYMENT.md)** — Frontend (Vercel), backend (Railway), env vars, custom domain
- **[API keys & env](docs/API-KEYS.md)** — All backend env vars and optional API keys per agent
- **[Architecture](docs/ARCHITECTURE.md)** — Pipeline, supervisor, agent pool, caching
- **[Agents](docs/AGENTS.md)** — Per-agent description, inputs, outputs
- **[Architecture & one-pager](docs/social-assets/one-pager.md)** — Diagram, design decisions, tech stack
- **[API reference](docs/API-REFERENCE.md)** — Backend REST endpoints

## Deployment

1. Set environment variables in your hosting platform (Vercel, Cloudflare Pages, etc.).
2. Build command: `npm run build` (runs `prebuild` → generates `public/sitemap.xml` with `lastmod`).
3. Output directory: `dist`.

**SEO (pre-rendered routes):** With prerender enabled (e.g. in CI), the build produces one HTML file per route. Fallback for unknown paths should be `index.html` for the SPA.

**OG image:** `public/og-image.png` is used for social/snippet previews (recommended 1200×630 px).

## Tech Stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui
- **Backend:** Python 3, FastAPI
- **Payments:** Stripe
- **Analytics:** Vercel Analytics

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to run locally, where to find docs, and how to report bugs or suggest features.

## License

[MIT](LICENSE)

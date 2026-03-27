/**
 * Agent definitions and data sources (aligned with backend agents).
 * Used for the "Agent Status" panel in the dashboard.
 */
export interface AgentSource {
  name: string;
  description?: string;
}

/** Backend result key for this agent (used to read timeout_or_error from analysis payload). */
export const AGENT_NAME_TO_KEY: Record<string, string> = {
  "FININT": "finint",
  "SIGINT": "sigint",
  "NEWS": "news",
  "GEOINT": "geoint",
  "SOCMINT": "socmint",
  "MEDIAINT": "mediaint",
  "TECHINT": "techint",
  "CYBER": "cyber",
  "ENERGY": "energy",
  "CHOKEPOINT": "chokepoint",
  "PROTEST": "protest",
  "DIPLO": "diplo",
  "PROXIMITY": "proximity",
  "PENTAGON": "pentagon",
  "SIGNAL FRAMEWORK": "narrative",
};

export interface AgentConfig {
  name: string;
  fullName: string;
  sources: AgentSource[];
}

export const AGENTS_WITH_SOURCES: AgentConfig[] = [
  {
    name: "FININT",
    fullName: "Financial Intelligence",
    sources: [
      { name: "Alpha Vantage", description: "Brent, WTI, VIX, Gold – oil and market indicators" },
      { name: "Polymarket", description: "Gamma API + Data API – conflict-related prediction markets" },
      { name: "Metaculus", description: "Metaculus API – forecast markets (conflict, military, nuclear)" },
      { name: "Kalshi", description: "Kalshi API – event markets (optional)" },
      { name: "Fear & Greed Index", description: "Alternative.me FNG API – market sentiment" },
      { name: "Metals API", description: "Gold (XAU) and metals (optional METALS_API_KEY)" },
      { name: "Polymarket Wallets", description: "Tracked wallet positions (e.g. rundeep)" },
      { name: "Etherscan", description: "On-chain wallet positions (optional ETHEREUM_ETHERSCAN_API_KEY)" },
    ],
  },
  {
    name: "SIGINT",
    fullName: "Signals Intelligence",
    sources: [
      { name: "ADS-B", description: "opendata.adsb.fi, api.adsb.lol – military aircraft (v2/mil + regions)" },
      { name: "Conflict Reports", description: "BBC, DW, Al Jazeera, CriticalThreats, LongWarJournal – conflict RSS" },
      { name: "NOTAMs", description: "Autorouter.aero / Eurocontrol (optional NOTAM_API_KEY)" },
      { name: "ADSBexchange", description: "Target aircraft via RapidAPI (optional ADSBEXCHANGE_RAPIDAPI_KEY)" },
    ],
  },
  {
    name: "NEWS",
    fullName: "News / OSINT",
    sources: [
      { name: "NewsAPI", description: "Trusted domains, conflict queries. Free: 100 req/day, 24h article delay" },
      { name: "RSS", description: "BBC, DW, Al Jazeera, RFE/RL, Iran International, Middle East Eye, CriticalThreats, LongWarJournal, ISW, Bellingcat, Crisis Group, ECFR, CSIS, FDD, France 24, Guardian" },
      { name: "NewsData", description: "NewsData.io – 200 credits/day, 10 articles/request; Location, Language, Category filters (optional NEWSDATA_API_KEY)" },
      { name: "GNews", description: "GNews (gnews.io) – 100 requests/day; q, lang, country (optional GNEWS_API_KEY)" },
    ],
  },
  {
    name: "GEOINT",
    fullName: "Geospatial Intelligence",
    sources: [
      { name: "NASA FIRMS", description: "Thermal anomalies, area API (middle_east, gaza_israel, iran, yemen, etc.)" },
      { name: "ReliefWeb/ACLED", description: "api.reliefweb.int/v2 + ACLED OAuth – humanitarian/conflict reports and events by country" },
      { name: "CrisisWatch", description: "International Crisis Group RSS stream for conflict trend monitoring and escalation context" },
      { name: "HDX HAPI", description: "hapi.humdata.org – operational presence, conflict events (optional HAPI_APP_IDENTIFIER)" },
      { name: "GDACS", description: "gdacs-api – disaster alerts (earthquakes, cyclones, floods, volcanoes) by region bbox" },
      { name: "EO Browser", description: "Sentinel Hub EO Browser links for satellite imagery (no key)" },
      { name: "GDELT GEO", description: "GDELT DOC/geo – country-level locations mentioned near conflict keywords (no key)" },
      { name: "ACLED Reference", description: "Curated ACLED analysis pages; Firecrawl or httpx (optional FIRECRAWL_API_KEY)" },
    ],
  },
  {
    name: "SOCMINT",
    fullName: "Social Media Intelligence",
    sources: [
      { name: "Telegram", description: "Public channels (t.me/s/…); scraping (fragile without API)" },
      { name: "Twitter/Nitter", description: "Twitter/X via Nitter instances – OSINT accounts" },
      { name: "Reddit", description: "Subreddits (geopolitics, worldnews, region-specific)" },
      { name: "RSS", description: "CriticalThreats, LongWarJournal, ISW, KyivPost, etc." },
      { name: "ReliefWeb", description: "Conflict reports by country" },
    ],
  },
  {
    name: "MEDIAINT",
    fullName: "Media Intelligence (SOCMINT images/video)",
    sources: [
      {
        name: "SOCMINT URLs",
        description: "Image/video links from Telegram, Twitter/X, and Reddit posts collected by SOCMINT",
      },
      { name: "EXIF & hashing", description: "Pillow EXIF (GPS, timestamps), perceptual hash for near-duplicate clustering" },
      { name: "Video keyframes", description: "FFmpeg extracts frames from short clips (optional local ffmpeg)" },
      {
        name: "Vision (Haiku)",
        description: "Claude Haiku on sampled frames stills (MEDIAINT_VISION_MAX_CALLS cap)",
      },
    ],
  },
  {
    name: "TECHINT",
    fullName: "Technical Intelligence",
    sources: [
      { name: "Tech indicators", description: "Alpha Vantage – tech ETF quotes (SMH, QQQ)" },
      { name: "Export control", description: "NewsAPI – export control, semiconductor sanctions news" },
      { name: "IODA", description: "IODA v2 API: outages, BGP/Ping/Telescope, alerts (Georgia Tech)" },
      { name: "OONI", description: "api.ooni.io – Telegram/Signal blocking (e.g. Iran)" },
      { name: "Shodan/Wigle", description: "Shodan host counts, Wigle WiFi/cellular (optional API keys)" },
      { name: "Cloudflare Radar", description: "Outage annotations (optional CLOUDFLARE_RADAR_API_TOKEN)" },
      { name: "Wayback Machine", description: "web.archive.org CDX – URL/domain change detection" },
    ],
  },
  {
    name: "CYBER",
    fullName: "Threat Intelligence",
    sources: [
      { name: "CISA KEV", description: "Known Exploited Vulnerabilities catalog (JSON feed, free)" },
      { name: "NVD", description: "NIST NVD – CVE/CVSS (services.nvd.nist.gov)" },
      { name: "InternetDB", description: "Shodan InternetDB – host/vuln lookup (internetdb.shodan.io)" },
      { name: "Threat RSS", description: "Mandiant, CrowdStrike – conflict-related APT reports" },
      { name: "AlienVault OTX", description: "Pulses/IoCs (optional OTX_API_KEY)" },
      { name: "GreyNoise", description: "GNQL stats: malicious scanners (7d), top actors/countries (optional GREYNOISE_API_KEY)" },
    ],
  },
  {
    name: "ENERGY",
    fullName: "Energy / Food & Commodities",
    sources: [
      { name: "Oil (EIA/FRED/AV)", description: "Brent, WTI – Alpha Vantage, EIA, FRED" },
      { name: "Food commodities", description: "Wheat, Corn, Soybean – Alpha Vantage" },
      { name: "FAO FPI", description: "Food Price Index (monthly CSV, free)" },
      { name: "Fertilizer", description: "World Bank – Urea, DAP (free API)" },
      {
        name: "World Bank Open Data",
        description: "Country macro: GDP, CPI, electricity access, poverty headcount (conflict → ISO3; open API)",
      },
    ],
  },
  {
    name: "CHOKEPOINT",
    fullName: "Maritime Chokepoint Monitor",
    sources: [
      { name: "AISStream/MT", description: "AISStream (optional AIRSTREAM_API_KEY), MarineTraffic, or AISHub – tanker positions" },
      { name: "GDELT", description: "GDELT DOC API – chokepoint/disruption query hits (24h/72h/6h, ToneChart optional)" },
      {
        name: "HDX Iran Port Activity",
        description: "HDX dataset: Iran daily port activity and shipment estimates (historical context for maritime monitoring)",
      },
      { name: "EIA baseline", description: "Persian Gulf oil export baseline (optional EIA_API_KEY)" },
      { name: "External status", description: "Optional CHOKEPOINT_STATUS_URL for external status feed" },
      { name: "AISHub", description: "Community AIS (optional AISHUB_USERNAME)" },
      { name: "MarineTraffic", description: "Area vessel queries (optional MARINETRAFFIC_API_KEY)" },
    ],
  },
  {
    name: "PROTEST",
    fullName: "Civil Society / Protest",
    sources: [
      { name: "ACLED", description: "Protests, riots (ACLED OAuth or API). Iran: acleddata.com/iran-crisis-live" },
      { name: "GDELT", description: "api.gdeltproject.org – protest-related articles (free)" },
    ],
  },
  {
    name: "DIPLO",
    fullName: "Diplomacy / Legal",
    sources: [
      { name: "OFAC SDN", description: "US Treasury SDN list (bulk CSV, free)" },
      {
        name: "EU sanctions",
        description:
          "EU Consolidated List dataset (data.europa.eu) – persons, groups, and entities subject to EU financial sanctions",
      },
      { name: "UN/ICJ", description: "UN Press RSS, ICJ press RSS – resolutions, court updates" },
    ],
  },
  {
    name: "PROXIMITY",
    fullName: "Strike–Civilian / Human-Shield",
    sources: [
      { name: "NASA FIRMS", description: "Thermal anomalies as strike triggers (VIIRS_SNPP_NRT)" },
      { name: "Overpass/OSM", description: "Schools, hospitals, government within 300 m" },
      { name: "Tunnel / military sites", description: "Optional GeoJSON (TUNNEL_SITES_GEOJSON_URL)" },
    ],
  },
  {
    name: "PENTAGON",
    fullName: "Pentagon-area informal signals (SerpAPI)",
    sources: [
      {
        name: "SerpAPI Google Maps",
        description:
          "Popular times / live busyness for configured DC-adjacent venues (pizza + nightlife proxies); anecdotal only",
      },
      {
        name: "SERPAPI_KEY",
        description: "Required for live fetches; optional PENTAGON_SIGNALS_MANUAL_SCORES for tests without API",
      },
      {
        name: "Caps",
        description: "PENTAGON_SIGNALS_SERPAPI_HOURLY_CAP / MONTHLY_CAP and quota file under backend/data",
      },
    ],
  },
  {
    name: "SIGNAL FRAMEWORK",
    fullName: "State vs. Exile Narrative",
    sources: [
      { name: "IRNA / Fars", description: "State-aligned Persian sources (RSS)" },
      { name: "Iran International / Radio Farda", description: "Exile/independent (RSS)" },
      { name: "Comparison", description: "Synthesis, latency, credibility gaps (Iran conflict)" },
    ],
  },
];

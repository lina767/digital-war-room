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
  "TECHINT": "techint",
  "CYBER": "cyber",
  "ENERGY": "energy",
  "CHOKEPOINT": "chokepoint",
  "PROTEST": "protest",
  "DIPLO": "diplo",
  "PROXIMITY": "proximity",
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
      { name: "Alpha Vantage", description: "Brent/WTI oil, tech ETF (SMH, QQQ)" },
      { name: "Polymarket", description: "Gamma API + Data API, conflict-related markets" },
      { name: "Tracked Wallets", description: "e.g. rundeep" },
      { name: "Metaculus", description: "Metaculus API – forecast markets (conflict, military, nuclear)" },
      { name: "Fear & Greed Index", description: "Alternative.me FNG API – market sentiment" },
      { name: "OFAC SDN", description: "Treasury bulk CSV – sanctions context for FININT (same as DIPLO)" },
      { name: "Metals API", description: "Gold (XAU) and metals prices (optional METALS_API_KEY)" },
      { name: "Etherscan", description: "On-chain wallet positions (optional ETHEREUM_ETHERSCAN_API_KEY)" },
    ],
  },
  {
    name: "SIGINT",
    fullName: "Signals Intelligence",
    sources: [
      { name: "ADSB", description: "opendata.adsb.fi, api.adsb.lol – military aircraft (v2/mil + regions)" },
      { name: "VesselFinder", description: "Naval vessels, bounding boxes (Persian Gulf, Red Sea, Med, Gulf of Aden)" },
      { name: "Spire Maritime", description: "AIS/vessels (optional SPIRE_MARITIME_API_KEY)" },
      { name: "Spire Airsafe", description: "Aircraft tracking stream (optional SPIRE_AIRSAFE_TOKEN)" },
      { name: "ADSBexchange", description: "Target aircraft via RapidAPI (optional ADSBEXCHANGE_RAPIDAPI_KEY)" },
      { name: "NOTAM", description: "Autorouter.aero / Eurocontrol – NOTAMs (optional NOTAM_API_KEY)" },
      { name: "IAEA", description: "IAEA news and press release feeds – Grossi/DG correlation" },
      { name: "RSS", description: "BBC, DW, Al Jazeera, CriticalThreats, LongWarJournal, UnderstandingWar – conflict reports" },
    ],
  },
  {
    name: "NEWS",
    fullName: "News / OSINT",
    sources: [
      { name: "NewsAPI", description: "Trusted domains, conflict queries. Free: 100 req/day, 24h article delay" },
      { name: "GDELT", description: "api.gdeltproject.org – 100+ languages, 65k+ sources" },
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
      { name: "ReliefWeb", description: "api.reliefweb.int/v2 – humanitarian/conflict reports by country" },
      { name: "UCDP", description: "Uppsala Conflict Data Program – GED events (optional UCDP_API_TOKEN)" },
      { name: "ACLED", description: "Conflict events (ACLED OAuth or API). Iran: acleddata.com/iran-crisis-live" },
      { name: "ACLED Reference", description: "Curated ACLED analysis pages (Middle East updates, expert comments); Firecrawl or httpx" },
      { name: "Firecrawl", description: "Robust scraping for ACLED reference pages (optional FIRECRAWL_API_KEY)" },
      { name: "GDELT GEO", description: "GDELT GEO 2.0 API – country-level map of locations mentioned near conflict keywords (no key)" },
    ],
  },
  {
    name: "SOCMINT",
    fullName: "Social Media Intelligence",
    sources: [
      { name: "Telegram", description: "Public channels (IranIntl, OSINTdefender, warmonitors, etc.)" },
      { name: "Nitter", description: "Twitter/X via Nitter instances – OSINT accounts" },
      { name: "Reddit", description: "Subreddits (geopolitics, worldnews, region-specific)" },
      { name: "RSS", description: "Region-specific (CriticalThreats, LongWarJournal, ISW, KyivPost, etc.)" },
      { name: "ReliefWeb", description: "Conflict reports by country" },
    ],
  },
  {
    name: "TECHINT",
    fullName: "Technical Intelligence",
    sources: [
      { name: "Alpha Vantage", description: "Tech ETF quotes (SMH, QQQ)" },
      { name: "NewsAPI", description: "Export control / semiconductor sanctions news" },
      { name: "IODA", description: "IODA v2 API: outages, BGP/Ping/Telescope signals, alerts, ASN entities (Georgia Tech)" },
      { name: "OONI", description: "api.ooni.io – Telegram/Signal blocking (e.g. Iran)" },
      { name: "Cloudflare Radar", description: "Outage annotations (optional CLOUDFLARE_RADAR_API_TOKEN)" },
      { name: "Shodan", description: "api.shodan.io – host counts, port breakdown (optional SHODAN_API_KEY)" },
      { name: "Wigle", description: "Wigle.net WiFi/cellular database (optional WIGLE_API_TOKEN)" },
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
      { name: "AGSI+", description: "EU gas storage (optional AGSI_API_KEY)" },
      { name: "Alpha Vantage", description: "Brent, WTI, Wheat, Corn, Soybean" },
      { name: "FAO FPI", description: "Food Price Index (monthly CSV, free)" },
      { name: "World Bank", description: "Fertilizer prices – Urea, DAP (free API)" },
    ],
  },
  {
    name: "CHOKEPOINT",
    fullName: "Maritime Chokepoint Monitor",
    sources: [
      { name: "Spire Maritime", description: "AIS tanker positions (optional SPIRE_MARITIME_API_KEY)" },
      { name: "AISHub", description: "Community AIS data (optional AISHUB_USERNAME)" },
      { name: "MarineTraffic", description: "Area vessel queries (optional MARINETRAFFIC_API_KEY)" },
      { name: "EIA API", description: "Persian Gulf oil export baseline (optional EIA_API_KEY)" },
      { name: "Compliance zones", description: "Hormuz, Bab el-Mandeb, Suez polygon zones" },
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
      { name: "EU Consolidated List", description: "EU sanctions XML (webgate.ec.europa.eu, open data)" },
      { name: "UN / ICJ", description: "UN Press RSS, ICJ press RSS – resolutions, court updates" },
    ],
  },
  {
    name: "PROXIMITY",
    fullName: "Strike–Civilian / Human-Shield",
    sources: [
      { name: "NASA FIRMS", description: "Thermal anomalies as strike triggers (VIIRS_SNPP_NRT)" },
      { name: "Overpass (OSM)", description: "Schools, hospitals, government within 300 m" },
      { name: "Tunnel / military sites", description: "Optional GeoJSON (TUNNEL_SITES_GEOJSON_URL) for human-shield flag" },
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

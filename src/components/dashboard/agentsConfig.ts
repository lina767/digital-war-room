/**
 * Agent definitions and data sources (aligned with backend agents).
 * Used for the "Agent Status" panel in the dashboard.
 */
export interface AgentSource {
  name: string;
  description?: string;
}

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
    ],
  },
  {
    name: "SIGINT",
    fullName: "Signals Intelligence",
    sources: [
      { name: "ADSB", description: "opendata.adsb.fi, api.adsb.lol – military aircraft (v2/mil + regions)" },
      { name: "VesselFinder", description: "Naval vessels, bounding boxes (Persian Gulf, Red Sea, Med, Gulf of Aden)" },
      { name: "Spire Maritime", description: "AIS/vessels (subagent; optional SPIRE_MARITIME_API_KEY)" },
      { name: "RSS", description: "CriticalThreats, LongWarJournal, UnderstandingWar – conflict reports" },
    ],
  },
  {
    name: "NEWS",
    fullName: "News / OSINT",
    sources: [
      { name: "NewsAPI", description: "Trusted domains, conflict queries" },
      { name: "GDELT", description: "api.gdeltproject.org – 100+ languages, 65k+ sources" },
      { name: "RSS", description: "Iran/MENA: CriticalThreats, LongWarJournal, ISW, Bellingcat, Crisis Group, ECFR, CSIS, FDD; Iran International, RFE/RL, BBC, Al Jazeera" },
    ],
  },
  {
    name: "GEOINT",
    fullName: "Geospatial Intelligence",
    sources: [
      { name: "NASA FIRMS", description: "Thermal anomalies, area API (middle_east, gaza_israel, iran, yemen, etc.)" },
      { name: "ReliefWeb", description: "api.reliefweb.int/v2 – humanitarian/conflict reports by country" },
      { name: "UCDP", description: "Uppsala Conflict Data Program – GED events (optional UCDP_API_TOKEN)" },
      { name: "ACLED", description: "Optional – conflict events (ACLED_API_KEY). Without key: acleddata.com/iran-crisis-live for Iran" },
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
      { name: "IODA", description: "Internet outage events (Georgia Tech)" },
      { name: "OONI", description: "Telegram/Signal blocking (e.g. Iran)" },
      { name: "Cloudflare Radar", description: "Outage annotations" },
      { name: "Shodan", description: "Host counts by country, port breakdown (502/22/443), vuln count" },
    ],
  },
];

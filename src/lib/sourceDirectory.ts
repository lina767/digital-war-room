/**
 * Source Directory – transparent, searchable list of all data sources with reliability ratings.
 * Built from agent config; reliability and API-key metadata defined here.
 */
import { AGENTS_WITH_SOURCES } from "@/components/dashboard/agentsConfig";

export type ReliabilityTier = "official" | "curated" | "community" | "supplementary";

export interface DataSourceEntry {
  id: string;
  name: string;
  description: string;
  agents: string[];
  reliability: ReliabilityTier;
  /** Whether an API key or auth is required for this source */
  keyRequired: boolean;
  /** Free to use (possibly with rate limits) */
  free: boolean;
  /** Optional URL for docs or registration */
  url?: string;
}

/** Reliability: Official = gov/institutions; Curated = verified APIs; Community = OSINT/open feeds; Supplementary = optional/auxiliary */
const RELIABILITY_LABELS: Record<ReliabilityTier, string> = {
  official: "Official",
  curated: "Curated",
  community: "Community",
  supplementary: "Supplementary",
};

/** Per-source metadata: reliability, key required, free, optional url */
const SOURCE_META: Record<
  string,
  { reliability: ReliabilityTier; keyRequired: boolean; free: boolean; url?: string }
> = {
  "Alpha Vantage": { reliability: "curated", keyRequired: true, free: true, url: "https://www.alphavantage.co/support/#api-key" },
  "Polymarket": { reliability: "curated", keyRequired: false, free: true, url: "https://polymarket.com" },
  "Tracked Wallets": { reliability: "community", keyRequired: false, free: true },
  "Metaculus": { reliability: "curated", keyRequired: false, free: true, url: "https://www.metaculus.com" },
  "Fear & Greed Index": { reliability: "community", keyRequired: false, free: true, url: "https://alternative.me/crypto/fear-and-greed-index/" },
  "Metals API": { reliability: "curated", keyRequired: true, free: true, url: "https://metals-api.com" },
  "Etherscan": { reliability: "curated", keyRequired: true, free: true, url: "https://etherscan.io/myapikey" },
  "ADS-B": { reliability: "community", keyRequired: false, free: true, url: "https://opendata.adsb.fi" },
  "Conflict Reports": { reliability: "community", keyRequired: false, free: true },
  NOTAMs: { reliability: "curated", keyRequired: true, free: false, url: "https://www.autorouter.aero" },
  ADSBexchange: { reliability: "community", keyRequired: true, free: false, url: "https://rapidapi.com/adsbx/api/adsbexchange-com1" },
  RSS: { reliability: "community", keyRequired: false, free: true },
  NewsAPI: { reliability: "curated", keyRequired: true, free: true, url: "https://newsapi.org/register" }, // Free: 100 req/day, 24h delay, no extra requests
  NewsData: { reliability: "curated", keyRequired: true, free: true, url: "https://newsdata.io/register" },
  GNews: { reliability: "curated", keyRequired: true, free: true, url: "https://gnews.io/register" },
  GDELT: { reliability: "curated", keyRequired: false, free: true, url: "https://api.gdeltproject.org" },
  "NASA FIRMS": { reliability: "official", keyRequired: true, free: true, url: "https://firms.modaps.eosdis.nasa.gov" },
  ReliefWeb: { reliability: "curated", keyRequired: false, free: true, url: "https://api.reliefweb.int" },
  "ReliefWeb/ACLED": { reliability: "curated", keyRequired: false, free: true, url: "https://api.reliefweb.int" },
  CrisisWatch: { reliability: "curated", keyRequired: false, free: true, url: "https://www.crisisgroup.org/crisiswatch" },
  "HDX HAPI": { reliability: "official", keyRequired: true, free: true, url: "https://data.humdata.org/hapi" },
  GDACS: { reliability: "official", keyRequired: false, free: true, url: "https://www.gdacs.org" },
  "EO Browser": { reliability: "curated", keyRequired: false, free: true, url: "https://apps.sentinel-hub.com/eo-browser" },
  "GDELT GEO": { reliability: "curated", keyRequired: false, free: true, url: "https://api.gdeltproject.org" },
  ACLED: { reliability: "curated", keyRequired: true, free: true, url: "https://acleddata.com/api-documentation/getting-started" },
  "ACLED Reference": { reliability: "curated", keyRequired: false, free: true, url: "https://acleddata.com" },
  Firecrawl: { reliability: "curated", keyRequired: true, free: true, url: "https://firecrawl.dev" },
  Telegram: { reliability: "community", keyRequired: false, free: true },
  "Twitter/Nitter": { reliability: "community", keyRequired: false, free: true },
  Nitter: { reliability: "community", keyRequired: false, free: true },
  Reddit: { reliability: "community", keyRequired: false, free: true },
  "Tech indicators": { reliability: "curated", keyRequired: true, free: true, url: "https://www.alphavantage.co/support/#api-key" },
  "Export control": { reliability: "curated", keyRequired: true, free: true, url: "https://newsapi.org" },
  "IODA": { reliability: "curated", keyRequired: false, free: true, url: "https://api.ioda.inetintel.cc.gatech.edu/v2/" },
  OONI: { reliability: "community", keyRequired: false, free: true, url: "https://ooni.org" },
  "Shodan/Wigle": { reliability: "community", keyRequired: false, free: true, url: "https://account.shodan.io" },
  "Cloudflare Radar": { reliability: "curated", keyRequired: true, free: true, url: "https://dash.cloudflare.com" },
  Shodan: { reliability: "community", keyRequired: false, free: true, url: "https://account.shodan.io" },
  Wigle: { reliability: "community", keyRequired: true, free: true, url: "https://wigle.net" },
  "Wayback Machine": { reliability: "community", keyRequired: false, free: true, url: "https://web.archive.org" },
  "CISA KEV": { reliability: "official", keyRequired: false, free: true, url: "https://www.cisa.gov/known-exploited-vulnerabilities-catalog" },
  NVD: { reliability: "official", keyRequired: false, free: true, url: "https://nvd.nist.gov" },
  InternetDB: { reliability: "community", keyRequired: false, free: true, url: "https://internetdb.shodan.io" },
  "Threat RSS": { reliability: "community", keyRequired: false, free: true },
  "AlienVault OTX": { reliability: "curated", keyRequired: true, free: true, url: "https://otx.alienvault.com" },
  "GreyNoise": { reliability: "curated", keyRequired: true, free: true, url: "https://www.greynoise.io" },
  "Oil (EIA/FRED/AV)": { reliability: "curated", keyRequired: true, free: true, url: "https://www.alphavantage.co/support/#api-key" },
  "Food commodities": { reliability: "curated", keyRequired: true, free: true, url: "https://www.alphavantage.co/support/#api-key" },
  "FAO FPI": { reliability: "official", keyRequired: false, free: true, url: "https://www.fao.org/worldfoodsituation/foodpricesindex/en/" },
  Fertilizer: { reliability: "official", keyRequired: false, free: true, url: "https://www.worldbank.org" },
  "World Bank Open Data": {
    reliability: "official",
    keyRequired: false,
    free: true,
    url: "https://data.worldbank.org",
  },
  "AISStream/MT": { reliability: "curated", keyRequired: true, free: false, url: "https://aisstream.io" },
  "HDX Iran Port Activity": {
    reliability: "official",
    keyRequired: false,
    free: true,
    url: "https://data.humdata.org/dataset/iran-islamic-republic-of-daily-port-activity-data-and-shipment-estimates",
  },
  "EIA baseline": { reliability: "curated", keyRequired: true, free: true, url: "https://www.eia.gov" },
  "External status": { reliability: "supplementary", keyRequired: false, free: true },
  MarineTraffic: { reliability: "curated", keyRequired: true, free: false, url: "https://www.marinetraffic.com" },
  AISHub: { reliability: "community", keyRequired: false, free: true, url: "https://www.aishub.net" },
  Kalshi: { reliability: "curated", keyRequired: false, free: true, url: "https://kalshi.com" },
  "Polymarket Wallets": { reliability: "community", keyRequired: false, free: true },
  "OFAC SDN": { reliability: "official", keyRequired: false, free: true, url: "https://ofac.treasury.gov" },
  "EU sanctions": {
    reliability: "official",
    keyRequired: false,
    free: true,
    url: "https://data.europa.eu/data/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions?locale=en",
  },
  "EU Consolidated List": {
    reliability: "official",
    keyRequired: false,
    free: true,
    url: "https://data.europa.eu/data/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions?locale=en",
  },
  "UN/ICJ": { reliability: "official", keyRequired: false, free: true },
  "UN / ICJ": { reliability: "official", keyRequired: false, free: true },
  "Overpass/OSM": { reliability: "community", keyRequired: false, free: true, url: "https://overpass-api.de" },
  "Overpass (OSM)": { reliability: "community", keyRequired: false, free: true, url: "https://overpass-api.de" },
  "Tunnel / military sites": { reliability: "supplementary", keyRequired: false, free: true },
};

function slug(name: string): string {
  return name
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "");
}

/** Build flat list of unique sources with reliability and agent associations */
export function buildSourceDirectory(): DataSourceEntry[] {
  const byName = new Map<string, { description: string; agents: string[] }>();

  for (const agent of AGENTS_WITH_SOURCES) {
    for (const src of agent.sources) {
      const name = src.name.trim();
      const desc = (src.description || "").trim();
      const existing = byName.get(name);
      if (existing) {
        if (!existing.agents.includes(agent.name)) existing.agents.push(agent.name);
        if (desc && desc.length > (existing.description?.length ?? 0)) existing.description = desc;
      } else {
        byName.set(name, { description: desc, agents: [agent.name] });
      }
    }
  }

  const entries: DataSourceEntry[] = [];
  for (const [name, { description, agents }] of byName.entries()) {
    const meta = SOURCE_META[name] ?? {
      reliability: "community" as ReliabilityTier,
      keyRequired: false,
      free: true,
    };
    entries.push({
      id: slug(name),
      name,
      description: description || "Data source used by one or more intelligence agents.",
      agents: agents.sort(),
      reliability: meta.reliability,
      keyRequired: meta.keyRequired,
      free: meta.free,
      url: meta.url,
    });
  }

  return entries.sort((a, b) => a.name.localeCompare(b.name));
}

export function getReliabilityLabel(tier: ReliabilityTier): string {
  return RELIABILITY_LABELS[tier] ?? tier;
}

export const SOURCE_DIRECTORY = buildSourceDirectory();

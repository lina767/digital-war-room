import type { AgentId } from "@/features/daily-briefing/types/briefing.types";

export const AGENTS: Record<
  AgentId,
  {
    id: AgentId;
    label: string;
    fullName: string;
    color: string;
    description: string;
    dataSources: string[];
  }
> = {
  FININT: {
    id: "FININT",
    label: "FININT",
    fullName: "Financial Intelligence",
    color: "var(--agent-finint)",
    description: "Tracks oil prices, defense stocks, prediction markets, and sanctions-related financial flows.",
    dataSources: ["Alpha Vantage", "EIA", "FRED", "Polymarket", "Yahoo Finance"],
  },
  SIGINT: {
    id: "SIGINT",
    label: "SIGINT",
    fullName: "Signals Intelligence",
    color: "var(--agent-sigint)",
    description: "Monitors military aviation and naval movements for anomaly patterns.",
    dataSources: ["ADS-B Exchange", "AISstream.io", "Eurocontrol IFPS"],
  },
  GEOINT: {
    id: "GEOINT",
    label: "GEOINT",
    fullName: "Geospatial Intelligence",
    color: "var(--agent-geoint)",
    description: "Detects thermal anomalies via satellite data and correlates with infrastructure.",
    dataSources: ["NASA FIRMS", "Overpass API"],
  },
  SOCMINT: {
    id: "SOCMINT",
    label: "SOCMINT",
    fullName: "Social Media Intelligence",
    color: "var(--agent-socmint)",
    description: "Monitors social channels for narrative shifts and information operations.",
    dataSources: ["Telegram", "Truth Social", "Reddit", "RSS feeds"],
  },
  NEWS: {
    id: "NEWS",
    label: "NEWS",
    fullName: "News Intelligence",
    color: "var(--agent-news)",
    description: "Aggregates and analyzes breaking news across trusted sources.",
    dataSources: ["NewsAPI", "Reuters", "AP", "BBC", "Al Jazeera"],
  },
  CYBER: {
    id: "CYBER",
    label: "CYBER",
    fullName: "Cyber Threat Intelligence",
    color: "var(--agent-cyber)",
    description: "Monitors internet background noise and targeted scanning activity.",
    dataSources: ["GreyNoise", "CISA KEV"],
  },
  ENERGY: {
    id: "ENERGY",
    label: "ENERGY",
    fullName: "Energy & Commodities",
    color: "var(--agent-energy)",
    description: "Tracks commodities, supply disruptions, and energy market stress.",
    dataSources: ["EIA API", "FRED API"],
  },
  DIPLO: {
    id: "DIPLO",
    label: "DIPLO",
    fullName: "Diplomatic Intelligence",
    color: "var(--agent-diplo)",
    description: "Monitors diplomatic signaling, sanctions updates, and multilateral messaging.",
    dataSources: ["State media RSS", "Sanctions feeds", "Official statements"],
  },
  PROXIMITY: {
    id: "PROXIMITY",
    label: "PROXIMITY",
    fullName: "Proximity Analyzer",
    color: "var(--agent-proximity)",
    description: "Correlates thermal events with civilian infrastructure for collateral-risk analysis.",
    dataSources: ["NASA FIRMS", "OpenStreetMap Overpass"],
  },
  TECHINT: {
    id: "TECHINT",
    label: "TECHINT",
    fullName: "Technical Intelligence",
    color: "var(--agent-techint)",
    description: "Tracks weapon systems, transfers, and dual-use technology signals.",
    dataSources: ["SIPRI", "Export-control datasets"],
  },
  CHOKEPOINT: {
    id: "CHOKEPOINT",
    label: "CHOKEPOINT",
    fullName: "Chokepoint Monitor",
    color: "var(--agent-chokepoint)",
    description: "Monitors Hormuz, Bab el-Mandeb, and Suez for disruptions and traffic stress.",
    dataSources: ["AISstream", "Maritime traffic APIs"],
  },
  GREYNOISE: {
    id: "GREYNOISE",
    label: "GREYNOISE",
    fullName: "GreyNoise Cyber Monitor",
    color: "var(--agent-greynoise)",
    description: "Internet-wide scan context for abnormal scanning and background threats.",
    dataSources: ["GreyNoise API"],
  },
};

export const AGENT_ORDER: AgentId[] = [
  "FININT",
  "SIGINT",
  "GEOINT",
  "SOCMINT",
  "NEWS",
  "CYBER",
  "ENERGY",
  "DIPLO",
  "PROXIMITY",
  "TECHINT",
  "CHOKEPOINT",
  "GREYNOISE",
];

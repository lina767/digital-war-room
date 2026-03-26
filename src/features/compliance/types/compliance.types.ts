export const MATCH_LEVEL_STYLES: Record<string, string> = {
  EXACT: "bg-destructive text-destructive-foreground",
  STRONG_FUZZY: "bg-orange-500/90 text-black",
  WEAK_FUZZY: "bg-yellow-400/80 text-black",
  REVIEW: "bg-muted text-muted-foreground",
};

export const RISK_LEVEL_STYLES: Record<string, string> = {
  CRITICAL: "bg-destructive text-destructive-foreground",
  HIGH: "bg-orange-500/90 text-black",
  MEDIUM: "bg-yellow-400/80 text-black",
  LOW: "bg-emerald-500/80 text-black",
};

export const DRIVER_SECTION_MAP: Record<string, string> = {
  CONFLICT_SANCTIONS_REGIME: "sanctions-lists",
  OFAC_SDN_EXTENSIVE: "sanctions-lists",
  OFAC_SDN_SIGNIFICANT: "sanctions-lists",
  OFAC_SDN_PRESENT: "sanctions-lists",
  EU_SANCTIONS_EXTENSIVE: "sanctions-lists",
  EU_SANCTIONS_PRESENT: "sanctions-lists",
  GEOFENCING_EMBARGO_ZONE: "geofencing-alerts",
  GEOFENCING_SANCTIONS_ZONE: "geofencing-alerts",
  AIS_SPOOFING: "ais-anomalies",
  AIS_DARK_ACTIVITY: "ais-anomalies",
};

export interface SanctionsResult {
  query: string;
  entity_name: string;
  matched_name: string;
  match_level: string;
  score: number;
  entity_type: string;
  program: string;
  source: string;
  ownership_chain?: Array<{ entity: string; parent: string; ownership_pct: number | null }>;
}

export interface SanctionsResponse {
  query: string;
  matches: SanctionsResult[];
  disclaimer: string;
  threshold_policy: Record<string, unknown>;
  screened_at?: string;
}

export interface SanctionsBatchResult {
  results: Array<{ query: string; matches: SanctionsResult[]; screened_at?: string; error?: string }>;
  threshold_policy: Record<string, unknown>;
  disclaimer: string;
}

export interface DocumentQAResponse {
  answer: string;
  confidence?: number;
  sources?: string[];
  disclaimer?: string;
}

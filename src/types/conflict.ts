import type { AgentMeta } from "@/lib/api";
import type { GeointAnomaly, SigintAircraft, SigintShip } from "@/types/theaterMap";
import type {
  ChokepointResult,
  CyberResult,
  DiploResult,
  EnergyResult,
  FinintResult,
  GeointResult as GeneratedGeointResult,
  NarrativeResult as GeneratedNarrativeResult,
  NewsResult as GeneratedNewsResult,
  ProximityResult,
  ProtestResult,
  SigintResult as GeneratedSigintResult,
  TechintResult,
} from "@/types/conflict.generated";

export type ConnectionStatus = "connecting" | "connected" | "analyzing" | "disconnected" | "error";

export interface NewsArticle {
  title?: string;
  url?: string;
  source?: string;
  publishedAt?: string;
  sentiment_label?: string;
  sentiment_score?: number;
}

export type PredictiveLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type PredictiveBasis = "baseline" | "data" | "markets" | "mixed";
export type PredictiveConfidence = "LOW" | "MEDIUM" | "HIGH";

export interface ProbabilityRange {
  min: number;
  max: number;
}

export interface EscalationForecast {
  horizon: string;
  level: PredictiveLevel;
  range?: ProbabilityRange;
  basis: PredictiveBasis;
  confidence: PredictiveConfidence;
  drivers: string[];
  vs_baseline: "higher" | "similar" | "lower";
  notes?: string;
}

export interface MarketForecast {
  instrument: string;
  horizon: string;
  level: PredictiveLevel;
  direction: "UP" | "DOWN" | "FLAT";
  range?: ProbabilityRange;
  basis: PredictiveBasis;
  confidence: PredictiveConfidence;
  drivers: string[];
  vs_baseline: "higher" | "similar" | "lower";
  notes?: string;
}

export interface PredictiveBlock {
  baseline_escalation?: EscalationForecast;
  escalation?: EscalationForecast[];
  markets?: MarketForecast[];
  market_benchmark?: MarketForecast[];
}

export interface RootCauseSuggestion {
  signal: string;
  likely_cause: string;
  confidence?: string;
}

export interface GeofencingAlert {
  asset_type: string;
  asset_id: string;
  asset_name: string;
  lat: number;
  lon: number;
  zone_name: string;
  zone_type: string;
  zone_source: string;
  timestamp: number;
  source: string;
  first_seen_at?: number;
  last_seen_at?: number;
  duration_hours?: number;
}

export interface AISAnomaly {
  asset_id: string;
  asset_name: string;
  anomaly_type: "spoofing" | "dark_activity";
  severity: string;
  detail: string;
  lat?: number;
  lon?: number;
  zone_name?: string;
  gap_hours?: number;
  last_seen_at?: number;
  confidence?: string;
}

export interface ComplianceRiskScore {
  level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  band: { min: number; max: number };
  numeric_score: number;
  drivers: Array<{
    factor: string;
    detail: string;
    impact: string;
    rule: string;
    programs?: string;
    note?: string;
  }>;
  disclaimer: string;
}

export interface OFACRecentAction {
  title?: string;
  url?: string;
  published?: string;
  source?: string;
  summary?: string;
}

export interface SigintWindowSummary {
  aircraft_count: number;
  ships_count: number;
  in_sanctions_zones: number;
}

export interface ComplianceBlock {
  geofencing_alerts?: GeofencingAlert[];
  ais_anomalies?: AISAnomaly[];
  risk_score?: ComplianceRiskScore;
  sigint_window_summary?: SigintWindowSummary;
  ofac_sdn?: { total_matches?: number; sample?: Array<{ name?: string; type?: string; program?: string }>; programs?: Array<{ name?: string; count?: number }>; error?: string | null };
  eu_sanctions?: { keyword_mentions?: number; error?: string | null };
  ofac_recent_actions?: OFACRecentAction[];
  disclaimer?: string;
}

type NewsBlock = GeneratedNewsResult & {
  articles?: NewsArticle[];
  _meta?: AgentMeta;
};

type FinintBlock = FinintResult & {
  polymarket_history?: number[][];
  polymarket_fetched_at?: string;
  timeout_or_error?: boolean;
  error?: string;
  _meta?: AgentMeta;
};

type GeointBlock = GeneratedGeointResult & {
  anomalies: GeointAnomaly[];
  _meta?: AgentMeta;
};

type SigintBlock = GeneratedSigintResult & {
  aircraft: SigintAircraft[];
  ships: SigintShip[];
  timeout_or_error?: boolean;
  error?: string;
  _meta?: AgentMeta;
};

type NarrativeBlock = GeneratedNarrativeResult & {
  signal_assessment?: { latency?: string; credibility_gaps?: string };
  signals?: {
    lexical?: { state_terms?: string[]; exile_terms?: string[]; interpretation?: string };
    latency?: string;
    discrepancy?: string;
    reaction?: string[];
  };
  anomalies?: string[];
  reaction_signals?: string[];
  theme_clusters?: Array<{
    theme?: string;
    summary?: string;
    passage_count?: number;
    consistency?: "high" | "medium" | "low" | string;
  }>;
  quoted_passages?: Array<{
    quote?: string;
    source_name?: string;
    timing?: string;
    context_note?: string;
    theme?: string;
  }>;
  negotiation_narrative_score?: number;
  method_notes?: string[];
  fetched_at?: string;
  error?: string;
  _meta?: AgentMeta;
};

export interface ConflictData {
  conflict: string;
  escalation_score: number | null;
  threat_level: string | null;
  key_findings: string[];
  root_cause_suggestions?: RootCauseSuggestion[];
  key_findings_context?: string[];
  key_findings_confidence?: string[];
  corroborated_patterns?: Array<{
    pattern_id?: string;
    summary?: string;
    agent_ids?: string[];
    evidence?: Array<{ agent: string; snippet_or_ref?: string }>;
  }>;
  scenarios: { description: string; probability: number }[];
  summary: string | null;
  narrative_story?: string | null;
  news?: NewsBlock;
  finint?: FinintBlock;
  geoint?: GeointBlock;
  sigint?: SigintBlock;
  techint?: TechintResult & { _meta?: AgentMeta };
  cyber?: CyberResult & { _meta?: AgentMeta };
  energy?: EnergyResult & { _meta?: AgentMeta };
  protest?: ProtestResult & { _meta?: AgentMeta };
  diplo?: DiploResult & { _meta?: AgentMeta };
  proximity?: ProximityResult & { _meta?: AgentMeta };
  narrative?: NarrativeBlock;
  chokepoint?: ChokepointResult & { _meta?: AgentMeta };
  agent_data_confidence?: Record<string, "live" | "estimated" | "degraded">;
  degraded_agents?: string[];
  pattern_flags?: Array<{
    id?: string;
    severity?: string;
    category?: string;
    title?: string;
    detail?: string;
    metrics?: Record<string, unknown>;
  }>;
  alerts?: Array<{ source: string; severity: string; text: string }>;
  actors?: Array<{
    id: string;
    name: string;
    role: string;
    activity: number;
    intelligence?: {
      official_position?: string;
      verified_actions?: string[];
      signals?: string[];
      military_profile?: string;
    };
  }>;
  predictive?: PredictiveBlock;
  compliance?: ComplianceBlock;
  /** Inline data URI for daily newsletter infographic (when generated). */
  _newsletter_infographic_data_uri?: string;
}

/* tslint:disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

/**
 * Common base fields shared by every agent result contract.
 */
export interface BaseAgentResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
}
export interface ChokepointResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  chokepoint_score?: number;
  chokepoints?: {
    [k: string]: unknown;
  }[];
  gdelt_disruption?: {
    [k: string]: unknown;
  };
  external_status?: {
    [k: string]: unknown;
  };
  data_confidence?: string;
}
export interface CyberResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  cyber_score?: number;
  cisa_kev?: {
    [k: string]: unknown;
  };
  threat_reports?: {
    [k: string]: unknown;
  }[];
  otx_pulses?: {
    [k: string]: unknown;
  }[];
  greynoise_scan_context?: {
    [k: string]: unknown;
  };
  internet_db?: {
    [k: string]: unknown;
  };
  fetched_at?: string;
}
export interface DiploResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  diplo_score?: number;
  ofac_sdn?: {
    [k: string]: unknown;
  };
  eu_sanctions?: {
    [k: string]: unknown;
  };
  un_icj_news?: {
    [k: string]: unknown;
  };
}
export interface EnergyResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  energy_score?: number;
  agsi_storage?: {
    [k: string]: unknown;
  };
  commodities?: {
    [k: string]: unknown;
  }[];
  food_commodities?: {
    [k: string]: unknown;
  }[];
  fao_fpi?: {
    [k: string]: unknown;
  };
  fertilizer?: {
    [k: string]: unknown;
  };
  /**
   * World Bank Open Data country snapshot (GDP, CPI, electricity access, poverty headcount).
   */
  world_bank_country?: {
    [k: string]: unknown;
  };
  food_security_risk?: number;
  global_impact_note?: string | null;
}
export interface FinintResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  escalation_score?: number;
  brent?: {
    [k: string]: unknown;
  } | null;
  wti?: {
    [k: string]: unknown;
  } | null;
  gold?: {
    [k: string]: unknown;
  } | null;
  vix?: {
    [k: string]: unknown;
  } | null;
  fear_greed?: {
    [k: string]: unknown;
  } | null;
  polymarket?: {
    [k: string]: unknown;
  }[];
  metaculus?: {
    [k: string]: unknown;
  }[];
  ofac_sanctions?: {
    [k: string]: unknown;
  };
  ofac_delta?: {
    [k: string]: unknown;
  } | null;
  tracked_wallets?: {
    [k: string]: unknown;
  }[];
  tracked_chain_wallets?: {
    [k: string]: unknown;
  }[];
  score_confidence?: {
    [k: string]: unknown;
  } | null;
  fetched_at?: string;
}
export interface GeointResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  geoint_score?: number;
  anomalies?: {
    [k: string]: unknown;
  }[];
  anomaly_count?: number;
  high_confidence_count?: number;
  explosion_count?: number;
  clusters?: {
    [k: string]: unknown;
  }[];
  hotspots?: {
    [k: string]: unknown;
  }[];
  reliefweb_reports?: {
    [k: string]: unknown;
  }[];
  eo_browser_links?: {
    [k: string]: unknown;
  }[];
  gdelt_geo_countries?: {
    [k: string]: unknown;
  }[];
}
export interface NarrativeResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  narrative_score?: number;
  source_comparison_table?: {
    [k: string]: unknown;
  }[];
  signal_assessment?: string;
  signals?: {
    [k: string]: unknown;
  }[];
  synthesis_probability?: number;
  synthesis_text?: string;
  anomalies?: {
    [k: string]: unknown;
  }[];
  lexical_state_terms?: string[];
  lexical_exile_terms?: string[];
  reaction_signals?: {
    [k: string]: unknown;
  }[];
  state_item_count?: number;
  exile_item_count?: number;
}
export interface NewsResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  news_score?: number;
  articles?: {
    [k: string]: unknown;
  }[];
  entities?: {
    [k: string]: unknown;
  }[];
  source_breakdown?: {
    [k: string]: number;
  };
  overall_sentiment?: number | null;
  sentiment_label?: string;
  top_sources?: {
    [k: string]: unknown;
  }[];
  escalation_headlines?: string[];
  escalation_score?: number;
}
export interface PentagonResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  pentagon_signals_score?: number;
  venues?: {
    [k: string]: unknown;
  }[];
  disclaimer?: string;
  data_confidence?: string;
  pentagon_score?: number;
}
export interface PentagonSignalsResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  pentagon_signals_score?: number;
  venues?: {
    [k: string]: unknown;
  }[];
  disclaimer?: string;
  data_confidence?: string;
}
export interface ProtestResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  protest_score?: number;
  protest_events?: {
    [k: string]: unknown;
  }[];
  protest_articles?: {
    [k: string]: unknown;
  }[];
  acled_aggregated?: {
    [k: string]: unknown;
  };
}
export interface ProximityResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  proximity_score?: number;
  evidence?: {
    [k: string]: unknown;
  }[];
  reason_empty?: string | null;
  error_message?: string | null;
}
export interface SatintelResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  satintel_score?: number;
  imagery_signals?: {
    [k: string]: unknown;
  }[];
  aoi?: {
    [k: string]: unknown;
  };
  copernicus_products?: {
    [k: string]: unknown;
  }[];
  source_status?: {
    [k: string]: unknown;
  };
}
export interface SigintResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  sigint_score?: number;
  aircraft?: {
    [k: string]: unknown;
  }[];
  ships?: {
    [k: string]: unknown;
  }[];
  hormuz_tankers?: {
    [k: string]: unknown;
  }[];
  hormuz_tanker_count?: number;
  conflict_reports?: {
    [k: string]: unknown;
  }[];
  notams?: {
    [k: string]: unknown;
  }[];
  alerts?: {
    [k: string]: unknown;
  }[];
  haiku_analysis?: string | null;
}
export interface SocmintResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  socmint_score?: number;
  telegram_posts?: {
    [k: string]: unknown;
  }[];
  twitter_posts?: {
    [k: string]: unknown;
  }[];
  reddit_posts?: {
    [k: string]: unknown;
  }[];
  rss_articles?: {
    [k: string]: unknown;
  }[];
  reliefweb_reports?: {
    [k: string]: unknown;
  }[];
  total_signals?: number;
  escalatory_count?: number;
  de_escalatory_count?: number;
  overall_sentiment?: number | null;
  top_signals?: {
    [k: string]: unknown;
  }[];
  entities?: {
    [k: string]: unknown;
  }[];
}
export interface TechintResult {
  schema_version?: number;
  conflict?: string;
  score?: number;
  summary?: string;
  content_hash?: string;
  dq_confidence?: number;
  data_freshness?: "live" | "recent" | "stale" | "unavailable";
  source_count?: number;
  fallback_used?: boolean;
  error_summary?: string | null;
  provenance_refs?: string[];
  techint_score?: number;
  tech_indicators?: {
    [k: string]: unknown;
  }[];
  export_controls?: {
    [k: string]: unknown;
  }[];
  ioda_events?: {
    [k: string]: unknown;
  }[];
  ioda_outages?: {
    [k: string]: unknown;
  }[];
  ioda_signals_raw?: {
    [k: string]: unknown;
  }[];
  ioda_alerts?: {
    [k: string]: unknown;
  }[];
  ioda_entities?: {
    [k: string]: unknown;
  }[];
  ooni?: {
    [k: string]: unknown;
  };
  cloudflare_outages?: {
    [k: string]: unknown;
  }[];
  shodan?: {
    [k: string]: unknown;
  };
  wayback?: {
    [k: string]: unknown;
  };
  whois_dns?: {
    [k: string]: unknown;
  };
  wigle?: {
    [k: string]: unknown;
  };
}

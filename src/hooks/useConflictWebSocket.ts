import { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import { getWsUrl, getLatestAnalysis, getAnalyzeStatus, triggerRefreshAnalysis, normalizeAnalysisResponse, type AnalyzeResponse, type AgentMeta } from "@/lib/api";
import type { GeointAnomaly, SigintAircraft, SigintShip } from "@/components/dashboard/mapConfig";

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

export interface ConflictData {
  conflict: string;
  escalation_score: number | null;
  threat_level: string | null;
  key_findings: string[];
  scenarios: { description: string; probability: number }[];
  summary: string | null;
  news?: {
    articles?: NewsArticle[];
    news_score?: number;
    summary?: string;
    source_breakdown?: { newsapi?: number; gdelt?: number; rss?: number; newsdata?: number; gnews?: number };
    _meta?: AgentMeta;
  };
  finint?: {
    brent?: { price: string; change_pct: string; as_of: string } | null;
    polymarket?: Array<{ question?: string; probability?: number; volume?: number; url?: string; end_date_iso?: string }>;
    polymarket_fetched_at?: string;
    timeout_or_error?: boolean;
    error?: string;
    _meta?: AgentMeta;
  };
  geoint?: {
    anomalies: GeointAnomaly[];
    geoint_score: number;
    _meta?: AgentMeta;
  };
  sigint?: {
    aircraft: SigintAircraft[];
    ships: SigintShip[];
    hormuz_tankers?: SigintShip[];
    hormuz_tanker_count?: number;
    conflict_reports?: { title: string; date?: string; url?: string; source?: string }[];
    sigint_score: number;
    timeout_or_error?: boolean;
    error?: string;
    _meta?: AgentMeta;
  };
  techint?: Record<string, unknown> & { _meta?: AgentMeta };
  cyber?: {
    cyber_score?: number;
    cisa_kev?: { total?: number; sample?: unknown[] };
    threat_reports?: Array<{ title?: string; url?: string }>;
    otx_pulses?: unknown[];
    greynoise_scan_context?: { available?: boolean; count?: number; top_actors?: unknown[]; top_source_countries?: unknown[] };
    summary?: string;
    _meta?: AgentMeta;
  };
  energy?: {
    energy_score?: number;
    agsi_storage?: { full?: Array<{ country?: string; full_pct?: number }> };
    commodities?: Array<{ symbol?: string; price?: string; change_pct?: string; change_pct_raw?: number }>;
    food_commodities?: Array<{ symbol?: string; label?: string; price?: string; change_pct?: string; change_pct_raw?: number }>;
    fao_fpi?: { index?: number; month?: string; yoy_change_pct?: number | null };
    fertilizer?: { urea_price?: number; dap_price?: number; source?: string };
    food_security_risk?: number;
    summary?: string;
    /** Set when conflict is Iran and oil move exceeds threshold (Hormuz/chokepoint risk). */
    global_impact_note?: string | null;
    _meta?: AgentMeta;
  };
  protest?: {
    protest_score?: number;
    protest_events?: unknown[];
    protest_articles?: Array<{ title?: string; url?: string }>;
    summary?: string;
    _meta?: AgentMeta;
  };
  diplo?: {
    diplo_score?: number;
    ofac_sdn?: { total_matches?: number; sample?: unknown[] };
    eu_sanctions?: { keyword_mentions?: number };
    un_icj_news?: Array<{ title?: string; url?: string; source?: string }>;
    summary?: string;
    _meta?: AgentMeta;
  };
  proximity?: {
    proximity_score?: number;
    evidence?: Array<{
      facilityName?: string;
      facilityType?: string;
      distanceMeters?: number;
      riskLabel?: string;
      summary?: string;
    }>;
    summary?: string;
    /** Why evidence is empty: no_strikes | no_facilities_near_strikes | error */
    reason_empty?: string;
    error_message?: string;
    _meta?: AgentMeta;
  };
  /** Signal Framework: state vs exile/independent media comparison (Iran). */
  narrative?: {
    conflict?: string;
    source_comparison_table?: Array<{
      point: string;
      state_narrative: string;
      exile_narrative: string;
      state_narrative_en?: string | null;
      exile_narrative_en?: string | null;
    }>;
    signal_assessment?: { latency?: string; credibility_gaps?: string };
    signals?: {
      lexical?: { state_terms?: string[]; exile_terms?: string[]; interpretation?: string };
      latency?: string;
      discrepancy?: string;
      reaction?: string[];
    };
    synthesis_probability?: number;
    synthesis_text?: string;
    anomalies?: string[];
    reaction_signals?: string[];
    state_item_count?: number;
    exile_item_count?: number;
    fetched_at?: string;
    error?: string;
    _meta?: AgentMeta;
  };
  chokepoint?: {
    chokepoints?: Array<{
      name: string;
      status: "OPEN" | "RESTRICTED" | "DISRUPTED";
      tanker_count: number;
      tanker_density: string;
      military_vessels: number;
      oil_flow_estimate_mbd: number;
      disruption_risk: number;
      ais_anomalies: number;
      brent_impact_pct: number;
      data_quality: "live_ais" | "estimated" | "baseline_only";
    }>;
    chokepoint_score?: number;
    summary?: string;
    _meta?: AgentMeta;
  };
  /** Centralised alerts from SIGINT, geofencing, AIS anomaly, GreyNoise. */
  alerts?: Array<{ source: string; severity: string; text: string }>;
  /** Iran conflict: actors with activity and optional intelligence (official position, verified actions, signals, military profile). */
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
  /** Unix timestamp; present when persistence is enabled (in-memory store). */
  first_seen_at?: number;
  /** Unix timestamp; present when persistence is enabled. */
  last_seen_at?: number;
  /** Hours in zone (last_seen_at - first_seen_at); present when persistence is enabled. */
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
  /** Hours between observations (spoofing) or since last seen (dark_activity). */
  gap_hours?: number;
  /** Unix timestamp of last AIS observation for this asset. */
  last_seen_at?: number;
  /** Heuristic strength: HIGH | MEDIUM. */
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

interface UseConflictWebSocketOptions {
  conflict: string;
  enabled?: boolean;
}

export function useConflictWebSocket({ conflict, enabled = true }: UseConflictWebSocketOptions) {
  const [data, setData] = useState<ConflictData | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [initialLoadPending, setInitialLoadPending] = useState<boolean>(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const conflictRef = useRef(conflict);
  conflictRef.current = conflict;

  const connect = useCallback(() => {
    if (!enabled) return;

    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }

    const wsUrl = getWsUrl(`/ws/${encodeURIComponent(conflictRef.current)}`);
    console.log("[WS] Connecting to", wsUrl);
    setStatus("connecting");

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] Connected");
      setStatus("connected");
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.status === "analyzing") {
          setStatus("analyzing");
        } else if (msg.status === "ok") {
          const next = normalizeAnalysisResponse(msg) as unknown as ConflictData;
          const alerts = next?.alerts ?? [];
          const highCount = alerts.filter((a) => (a.severity || "").toLowerCase() === "high" || (a.severity || "").toLowerCase() === "critical").length;
          if (highCount > 0) {
            toast.info(`${highCount} alert(s)`, { description: alerts[0]?.text?.slice(0, 80) ?? "New intelligence alerts" });
          }
          setData(next);
          setLastUpdated(new Date());
          setStatus("connected");
          setAnalysisError(null);
        } else if (msg.status === "error") {
          console.error("[WS] Server error:", msg.message);
          setStatus("error");
        }
      } catch (e) {
        console.error("[WS] Parse error:", e);
      }
    };

    ws.onerror = () => {
      setStatus("error");
    };

    ws.onclose = () => {
      console.log("[WS] Disconnected - reconnecting in 5s");
      setStatus("disconnected");
      reconnectTimer.current = setTimeout(connect, 5000);
    };
  }, [enabled]);

  // On load fetch cached result; retry if no cache yet
  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    setAnalysisError(null);
    setInitialLoadPending(true);

    const attempt = (retryCount: number) => {
      getLatestAnalysis(conflict).then((cached) => {
        if (cancelled) return;
        if (cached) {
          setData(normalizeAnalysisResponse(cached as Record<string, unknown>) as unknown as ConflictData);
          setLastUpdated(new Date());
          setAnalysisError(null);
          setInitialLoadPending(false);
        } else {
          getAnalyzeStatus(conflict).then((statusRes) => {
            if (cancelled) return;
            if (statusRes === null) {
              setAnalysisError("Backend unreachable. Check VITE_API_URL (e.g. Railway URL) or start the backend.");
              setInitialLoadPending(false);
            } else if (!statusRes.cached) {
              setAnalysisError("First analysis still running – data will appear automatically shortly.");
              setInitialLoadPending(false);
              if (retryCount < 12) {
                const delay = Math.min(10_000, 3_000 + retryCount * 1_000);
                retryTimer = setTimeout(() => attempt(retryCount + 1), delay);
              }
            } else {
              setInitialLoadPending(false);
            }
          }).catch(() => { if (!cancelled) setInitialLoadPending(false); });
        }
      }).catch(() => {
        if (!cancelled) setInitialLoadPending(false);
      });
    };

    attempt(0);
    return () => { cancelled = true; if (retryTimer) clearTimeout(retryTimer); };
  }, [conflict]);

  // Every 2 min fetch cached result (shows updates from auto-run)
  useEffect(() => {
    const interval = setInterval(() => {
      getLatestAnalysis(conflict).then((cached) => {
        if (cached) {
          setData(normalizeAnalysisResponse(cached as Record<string, unknown>) as unknown as ConflictData);
          setLastUpdated(new Date());
          setAnalysisError(null);
        }
      });
    }, 120_000);
    return () => clearInterval(interval);
  }, [conflict]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect, conflict]);

  const refresh = useCallback(() => {
    connect();
  }, [connect]);

  /** Fetches cached analysis; if none, triggers background refresh and polls. */
  const runAnalysis = useCallback(async (): Promise<AnalyzeResponse | null> => {
    if (!enabled) return null;
    setAnalysisError(null);
    setStatus("analyzing");
    try {
      const result = await getLatestAnalysis(conflictRef.current);
      if (result) {
        setData(result as unknown as ConflictData);
        setLastUpdated(new Date());
        setStatus("connected");
        setAnalysisError(null);
        return result;
      }
      const statusRes = await getAnalyzeStatus(conflictRef.current);
      if (statusRes === null) {
        setAnalysisError("Backend unreachable. Check VITE_API_URL (e.g. Railway URL) or start the backend.");
        setStatus("error");
        return null;
      }
      if (statusRes.error) {
        setAnalysisError(`Last analysis failed: ${statusRes.error} Starting new analysis…`);
      } else {
        setAnalysisError("Analysis started – loading data (may take 2–5 min)…");
      }
      await triggerRefreshAnalysis(conflictRef.current);
      const maxPolls = 48; // 48 × 5s = 4 min
      for (let i = 0; i < maxPolls; i++) {
        await new Promise((r) => setTimeout(r, 5_000));
        const statusRes = await getAnalyzeStatus(conflictRef.current);
        if (statusRes?.error) {
          setAnalysisError(`Analysis failed: ${statusRes.error}`);
          setStatus("error");
          return null;
        }
        const fresh = await getLatestAnalysis(conflictRef.current);
        if (fresh) {
          setData(fresh as unknown as ConflictData);
          setLastUpdated(new Date());
          setStatus("connected");
          setAnalysisError(null);
          return fresh;
        }
      }
      const finalStatus = await getAnalyzeStatus(conflictRef.current);
      if (finalStatus?.error) {
        setAnalysisError(`Analysis failed: ${finalStatus.error}`);
      } else {
        setAnalysisError("Analysis is taking longer than expected. Reload the page or try again later.");
      }
      setStatus(finalStatus?.error ? "error" : "connected");
      return null;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error("[Analysis]", err);
      setAnalysisError(message);
      setStatus("error");
      return null;
    }
  }, [enabled]);

  return { data, status, lastUpdated, analysisError, initialLoadPending, refresh, runAnalysis, setData };
}

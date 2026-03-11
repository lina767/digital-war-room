import { useEffect, useRef, useState, useCallback } from "react";
import { getWsUrl, getLatestAnalysis, getAnalyzeStatus, normalizeAnalysisResponse, type AnalyzeResponse } from "@/lib/api";

export type ConnectionStatus = "connecting" | "connected" | "analyzing" | "disconnected" | "error";

export interface NewsArticle {
  title?: string;
  url?: string;
  source?: string;
  publishedAt?: string;
  sentiment_label?: string;
  sentiment_score?: number;
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
    source_breakdown?: { newsapi?: number; gdelt?: number; rss?: number };
  };
  finint?: {
    brent?: { price: string; change_pct: string; as_of: string } | null;
    polymarket?: Array<{ question?: string; probability?: number; volume?: number; url?: string }>;
  };
  geoint?: {
    anomalies: any[];
    geoint_score: number;
  };
  sigint?: {
    aircraft: any[];
    ships: any[];
    conflict_reports?: { title: string; date?: string; url?: string; source?: string }[];
    sigint_score: number;
  };
  techint?: Record<string, unknown>;
  cyber?: {
    cyber_score?: number;
    cisa_kev?: { total?: number; sample?: unknown[] };
    threat_reports?: Array<{ title?: string; url?: string }>;
    otx_pulses?: unknown[];
    greynoise_scan_context?: { available?: boolean; count?: number; top_actors?: unknown[]; top_source_countries?: unknown[] };
    summary?: string;
  };
  energy?: {
    energy_score?: number;
    agsi_storage?: { full?: Array<{ country?: string; full_pct?: number }> };
    commodities?: Array<{ symbol?: string; price?: string; change_pct?: string }>;
    summary?: string;
    /** Set when conflict is Iran and oil move exceeds threshold (Hormuz/chokepoint risk). */
    global_impact_note?: string | null;
  };
  protest?: {
    protest_score?: number;
    protest_events?: unknown[];
    protest_articles?: Array<{ title?: string; url?: string }>;
    summary?: string;
  };
  diplo?: {
    diplo_score?: number;
    ofac_sdn?: { total_matches?: number; sample?: unknown[] };
    eu_sanctions?: { keyword_mentions?: number };
    un_icj_news?: Array<{ title?: string; url?: string; source?: string }>;
    summary?: string;
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
  };
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
          setData(normalizeAnalysisResponse(msg) as unknown as ConflictData);
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

  // Beim Laden gecachtes Ergebnis holen; initialLoadPending bleibt true bis Antwort (unabhängig vom WebSocket-Status)
  useEffect(() => {
    let cancelled = false;
    setAnalysisError(null);
    setInitialLoadPending(true);
    getLatestAnalysis(conflict).then((cached) => {
      if (cancelled) return;
      if (cached) {
        setData(normalizeAnalysisResponse(cached as Record<string, unknown>) as unknown as ConflictData);
        setLastUpdated(new Date());
        setAnalysisError(null);
      } else {
        getAnalyzeStatus(conflict).then((statusRes) => {
          if (cancelled) return;
          if (statusRes === null) {
            setAnalysisError("Backend nicht erreichbar. VITE_API_URL prüfen (Railway-URL) oder Backend starten.");
          } else if (!statusRes.cached) {
            setAnalysisError("First analysis still running – data will appear automatically shortly.");
          }
        }).catch(() => { /* keep pending false */ });
      }
      setInitialLoadPending(false);
    }).catch(() => {
      if (!cancelled) setInitialLoadPending(false);
    });
    return () => { cancelled = true; };
  }, [conflict]);

  // Alle 2 Min gecachtes Ergebnis abrufen (zeigt Updates vom 10-Min-Auto-Run)
  useEffect(() => {
    const interval = setInterval(() => {
      getLatestAnalysis(conflict).then((cached) => {
        if (cached) {
          setData(normalizeAnalysisResponse(cached as Record<string, unknown>) as unknown as ConflictData);
          setLastUpdated(new Date());
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

  /** Holt die gecachte Analyse (GET /api/analyze/latest). Wie beim Start – keine neue Analyse, nur Cache. */
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
      setStatus("connected");
      const status = await getAnalyzeStatus(conflictRef.current);
      if (status === null) {
        setAnalysisError("Backend nicht erreichbar. VITE_API_URL prüfen (Railway-URL) oder Backend starten.");
      }
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

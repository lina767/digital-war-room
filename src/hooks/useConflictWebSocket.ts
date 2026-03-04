import { useEffect, useRef, useState, useCallback } from "react";
import { getWsUrl, runAnalysis as runAnalysisApi, normalizeAnalysisResponse, type AnalyzeResponse } from "@/lib/api";

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
    polymarket?: Array<{ question?: string; probability?: number; url?: string }>;
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
}

interface UseConflictWebSocketOptions {
  conflict: string;
  enabled?: boolean;
}

export function useConflictWebSocket({ conflict, enabled = true }: UseConflictWebSocketOptions) {
  const [data, setData] = useState<ConflictData | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
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
          setData(normalizeAnalysisResponse(msg) as ConflictData);
          setLastUpdated(new Date());
          setStatus("connected");
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

  /** Run analysis via REST POST /api/analyze and update data (for "Run Analysis" button). */
  const runAnalysis = useCallback(async (): Promise<AnalyzeResponse | null> => {
    if (!enabled) return null;
    setAnalysisError(null);
    setStatus("analyzing");
    try {
      const result = await runAnalysisApi(conflictRef.current);
      setData(result as ConflictData);
      setLastUpdated(new Date());
      setStatus("connected");
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error("[Analysis]", err);
      setAnalysisError(message);
      setStatus("error");
      return null;
    }
  }, [enabled]);

  return { data, status, lastUpdated, analysisError, refresh, runAnalysis, setData };
}

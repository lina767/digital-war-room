import { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import { getWsUrl, getLatestAnalysis, getAnalyzeStatus, triggerRefreshAnalysis, normalizeAnalysisResponse, type AnalyzeResponse } from "@/lib/api";
import type { ConflictData, ConnectionStatus } from "@/types/conflict";
export type {
  AISAnomaly,
  ComplianceBlock,
  ComplianceRiskScore,
  ConflictData,
  ConnectionStatus,
  EscalationForecast,
  GeofencingAlert,
  PredictiveBlock,
  PredictiveLevel,
  RootCauseSuggestion,
} from "@/types/conflict";

interface UseConflictWebSocketOptions {
  conflict: string;
  enabled?: boolean;
}

export function useConflictWebSocket({ conflict, enabled = true }: UseConflictWebSocketOptions) {
  const [data, setData] = useState<ConflictData | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [initialLoadPending, setInitialLoadPending] = useState<boolean>(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [dataFromCache, setDataFromCache] = useState<boolean>(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const conflictRef = useRef(conflict);
  conflictRef.current = conflict;
  const sameConflict = useCallback((incoming: unknown) => {
    if (typeof incoming !== "string") return false;
    return incoming.trim().toLowerCase() === conflictRef.current.trim().toLowerCase();
  }, []);

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
        if (!sameConflict(msg.conflict)) return;
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
          setDataFromCache(false);
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
  }, [enabled, sameConflict]);

  // On load fetch cached result; retry if no cache yet
  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    setAnalysisError(null);
    setInitialLoadPending(true);

    const attempt = (retryCount: number) => {
      getLatestAnalysis(conflict).then((result) => {
        if (cancelled) return;
        if (result.data) {
          setData(normalizeAnalysisResponse(result.data as Record<string, unknown>) as unknown as ConflictData);
          setLastUpdated(new Date());
          setDataFromCache(result.fromCache);
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
    if (!enabled) return;
    const interval = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      getLatestAnalysis(conflict).then((result) => {
        if (result.data) {
          setData(normalizeAnalysisResponse(result.data as Record<string, unknown>) as unknown as ConflictData);
          setLastUpdated(new Date());
          setDataFromCache(result.fromCache);
          setAnalysisError(null);
        }
      });
    }, 120_000);
    return () => clearInterval(interval);
  }, [conflict, enabled]);

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
      const { data: latest, fromCache } = await getLatestAnalysis(conflictRef.current);
      if (latest) {
        setData(latest as unknown as ConflictData);
        setLastUpdated(new Date());
        setDataFromCache(fromCache);
        setStatus("connected");
        setAnalysisError(null);
        return latest;
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
      // Backend ANALYZE_TIMEOUT_SEC = 300s; poll long enough to outlast a full run + cache write.
      const maxPolls = 72; // 72 × 5s = 6 min
      for (let i = 0; i < maxPolls; i++) {
        await new Promise((r) => setTimeout(r, 5_000));
        const statusRes = await getAnalyzeStatus(conflictRef.current);
        if (statusRes?.error) {
          setAnalysisError(`Analysis failed: ${statusRes.error}`);
          setStatus("error");
          return null;
        }
        const { data: fresh, fromCache } = await getLatestAnalysis(conflictRef.current);
        if (fresh) {
          setData(fresh as unknown as ConflictData);
          setLastUpdated(new Date());
          setDataFromCache(fromCache);
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

  return { data, status, lastUpdated, dataFromCache, analysisError, initialLoadPending, refresh, runAnalysis, setData };
}

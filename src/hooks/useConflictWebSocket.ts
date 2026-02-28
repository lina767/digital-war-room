import { useEffect, useRef, useState, useCallback } from "react";

export type ConnectionStatus = "connecting" | "connected" | "analyzing" | "disconnected" | "error";

export interface ConflictData {
  conflict: string;
  escalation_score: number | null;
  threat_level: string | null;
  key_findings: string[];
  scenarios: { description: string; probability: number }[];
  summary: string | null;
  finint?: {
    brent?: { price: string; change_pct: string; as_of: string } | null;
  };
  geoint?: {
    anomalies: any[];
    geoint_score: number;
  };
  sigint?: {
    aircraft: any[];
    ships: any[];
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

    const wsUrl = `ws://localhost:8000/ws/${encodeURIComponent(conflictRef.current)}`;
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
          setData(msg);
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

  return { data, status, lastUpdated, refresh, setData };
}

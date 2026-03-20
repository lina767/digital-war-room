import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getWsUrl } from "@/lib/api";

export interface SocialSignal {
  source?: string;
  text?: string;
  title?: string;
  url?: string;
  platform?: "twitter" | "telegram" | "reddit" | string;
  account?: string;
  upvotes?: number;
  sentiment_score?: number;
  sentiment_label?: string;
  published_at?: string;
}

interface SocialWsPayload {
  status: "ok" | "error";
  conflict?: string;
  fetched_at?: string;
  twitter?: SocialSignal[];
  telegram?: SocialSignal[];
  reddit?: SocialSignal[];
  message?: string;
}

export function useSocialWebSocket(conflict: string, enabled = true) {
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected" | "error">("disconnected");
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [twitter, setTwitter] = useState<SocialSignal[]>([]);
  const [telegram, setTelegram] = useState<SocialSignal[]>([]);
  const [reddit, setReddit] = useState<SocialSignal[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const conflictRef = useRef(conflict);
  conflictRef.current = conflict;

  const connect = useCallback(() => {
    if (!enabled) return;
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }
    setStatus("connecting");
    const ws = new WebSocket(getWsUrl(`/ws/social/${encodeURIComponent(conflictRef.current)}`));
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("connected");
      setError(null);
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as SocialWsPayload;
        if (msg.status === "error") {
          setStatus("error");
          setError(msg.message ?? "Social monitoring stream error");
          return;
        }
        setTwitter(Array.isArray(msg.twitter) ? msg.twitter : []);
        setTelegram(Array.isArray(msg.telegram) ? msg.telegram : []);
        setReddit(Array.isArray(msg.reddit) ? msg.reddit : []);
        setLastUpdated(new Date());
        setStatus("connected");
        setError(null);
      } catch {
        setStatus("error");
        setError("Invalid social monitoring payload");
      }
    };

    ws.onerror = () => {
      setStatus("error");
      setError("Social monitoring connection error");
    };

    ws.onclose = () => {
      setStatus("disconnected");
      reconnectRef.current = setTimeout(connect, 5000);
    };
  }, [enabled]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect, conflict]);

  const combined = useMemo(() => [...twitter, ...telegram, ...reddit], [twitter, telegram, reddit]);

  return { status, error, lastUpdated, twitter, telegram, reddit, combined };
}

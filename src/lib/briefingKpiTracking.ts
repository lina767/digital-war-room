import { track } from "@vercel/analytics";
import { hasAnalyticsConsent } from "@/lib/analyticsConsent";
import { newsletterTrackEvent } from "@/lib/api/newsletter";

const LAST_NEWSLETTER_TOUCH_KEY = "dwr_last_newsletter_touch_at";
const SESSION_KEY = "dwr_kpi_session_id";
const RETURN_WINDOW_MS = 24 * 60 * 60 * 1000;

function getSessionId(): string {
  if (typeof window === "undefined") return "server";
  const existing = window.sessionStorage.getItem(SESSION_KEY);
  if (existing) return existing;
  const generated = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  window.sessionStorage.setItem(SESSION_KEY, generated);
  return generated;
}

export function getUtmContext(): { campaign?: string; utmContent?: string; source?: string; medium?: string } {
  if (typeof window === "undefined") return {};
  const search = new URLSearchParams(window.location.search);
  return {
    campaign: search.get("utm_campaign") ?? undefined,
    utmContent: search.get("utm_content") ?? undefined,
    source: search.get("utm_source") ?? undefined,
    medium: search.get("utm_medium") ?? undefined,
  };
}

export function trackKpiEvent(
  eventType: string,
  payload: {
    conflict?: string;
    campaign?: string;
    utmContent?: string;
    ttvSeconds?: number;
    meta?: Record<string, unknown>;
  } = {},
): void {
  if (!hasAnalyticsConsent()) return;
  const sessionId = getSessionId();
  track(eventType, {
    conflict: payload.conflict,
    campaign: payload.campaign,
    utm_content: payload.utmContent,
    ttv_seconds: payload.ttvSeconds,
  });
  void newsletterTrackEvent({
    event_type: eventType,
    event_source: "web",
    campaign: payload.campaign,
    utm_content: payload.utmContent,
    conflict: payload.conflict,
    session_id: sessionId,
    path: typeof window !== "undefined" ? window.location.pathname : "/daily-briefing",
    ttv_seconds: payload.ttvSeconds,
  }).catch(() => {
    // Keep UI non-blocking when telemetry endpoint is unavailable.
  });
}

export function markNewsletterTouchNow(): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LAST_NEWSLETTER_TOUCH_KEY, String(Date.now()));
}

export function shouldCountAs24hReturn(): boolean {
  if (typeof window === "undefined") return false;
  const raw = window.localStorage.getItem(LAST_NEWSLETTER_TOUCH_KEY);
  if (!raw) return false;
  const at = Number(raw);
  if (!Number.isFinite(at)) return false;
  return Date.now() - at <= RETURN_WINDOW_MS;
}

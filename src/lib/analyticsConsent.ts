export type AnalyticsConsent = "granted" | "denied";

const STORAGE_KEY = "dwr_analytics_consent";

export function getAnalyticsConsent(): AnalyticsConsent | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw === "granted" || raw === "denied") return raw;
  return null;
}

export function setAnalyticsConsent(value: AnalyticsConsent): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, value);
}

export function hasAnalyticsConsent(): boolean {
  return getAnalyticsConsent() === "granted";
}


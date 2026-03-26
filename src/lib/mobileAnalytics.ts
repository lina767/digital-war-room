import { track } from "@vercel/analytics";
import { hasAnalyticsConsent } from "@/lib/analyticsConsent";

/** Matches Tailwind `lg` (desktop unchanged above this width). */
const MOBILE_MAX_WIDTH = 1023;

export function isMobileViewport(): boolean {
  if (typeof window === "undefined") return false;
  return window.innerWidth <= MOBILE_MAX_WIDTH;
}

export function isPwaStandalone(): boolean {
  if (typeof window === "undefined") return false;
  if (window.matchMedia("(display-mode: standalone)").matches) return true;
  const nav = window.navigator as Navigator & { standalone?: boolean };
  return nav.standalone === true;
}

type MobileEventPayload = Record<string, string | number | boolean | undefined>;

/**
 * Fires Vercel Analytics custom events only on mobile viewports so desktop metrics stay clean.
 */
export function trackMobileEvent(name: string, payload?: MobileEventPayload): void {
  if (!hasAnalyticsConsent()) return;
  if (!isMobileViewport()) return;
  track(name, {
    ...payload,
    mobile: true,
    standalone: isPwaStandalone(),
  });
}

export function trackMobilePageView(pathname: string): void {
  trackMobileEvent("mobile_page_view", { path: pathname });
}

export function trackMobileNav(action: "open" | "close"): void {
  trackMobileEvent("mobile_nav_menu", { action });
}

export function trackMobilePanel(side: "left" | "right", action: "open" | "close"): void {
  trackMobileEvent("mobile_side_panel", { side, action });
}

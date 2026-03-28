import type { IntelStorySnapshot } from "./types";

/** Encode snapshot for URL hash (client-only; keep payload small). */
export function encodeIntelStoryHash(snapshot: IntelStorySnapshot): string {
  const json = JSON.stringify(snapshot);
  const b64 = typeof btoa !== "undefined" ? btoa(unescape(encodeURIComponent(json))) : "";
  return `intelStory=${encodeURIComponent(b64)}`;
}

export function decodeIntelStoryHash(hashFragment: string): IntelStorySnapshot | null {
  try {
    const h = hashFragment.replace(/^#/, "").trim();
    if (!h.startsWith("intelStory=")) return null;
    const raw = decodeURIComponent(h.slice("intelStory=".length));
    const json = decodeURIComponent(escape(atob(raw)));
    const parsed = JSON.parse(json) as IntelStorySnapshot;
    if (parsed?.v !== 1 || typeof parsed.conflict !== "string") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function buildIntelStoryShareUrl(snapshot: IntelStorySnapshot): string {
  const path = `${window.location.origin}/app/dashboard`;
  return `${path}#${encodeIntelStoryHash(snapshot)}`;
}

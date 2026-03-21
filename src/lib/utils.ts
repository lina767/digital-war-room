import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Safe message from caught errors (API, forms, hooks). */
export function getErrorMessage(err: unknown, fallback = "Something went wrong."): string {
  return err instanceof Error ? err.message : fallback;
}

/**
 * Format a date as relative time (e.g. "Just now", "5m ago", "2h ago", "3d ago").
 * @param date - Date object, ISO string, or null/undefined
 * @param addSuffix - If true (default), append " ago". If false, return "5m" only.
 */
export function formatTimeAgo(
  date: Date | string | null | undefined,
  addSuffix = true,
): string {
  if (date == null) return "—";
  const ms = typeof date === "string" ? new Date(date).getTime() : date.getTime();
  if (Number.isNaN(ms)) return "—";
  const sec = Math.floor((Date.now() - ms) / 1000);
  if (sec < 60) return addSuffix ? "Just now" : "now";
  if (sec < 3600) {
    const m = Math.floor(sec / 60);
    return addSuffix ? `${m}m ago` : `${m}m`;
  }
  if (sec < 86400) {
    const h = Math.floor(sec / 3600);
    return addSuffix ? `${h}h ago` : `${h}h`;
  }
  const d = Math.floor(sec / 86400);
  return addSuffix ? `${d}d ago` : `${d}d`;
}

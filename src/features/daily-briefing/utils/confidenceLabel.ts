import type { ConfidenceLevel } from "@/features/daily-briefing/types/briefing.types";

export function normalizeConfidence(input: string | null | undefined): ConfidenceLevel {
  const value = (input ?? "").trim().toUpperCase();
  if (value === "HIGH") return "HIGH";
  if (value === "LOW") return "LOW";
  return "MEDIUM";
}

export function confidenceClass(level: ConfidenceLevel): string {
  if (level === "HIGH") return "text-emerald-300";
  if (level === "LOW") return "text-rose-300";
  return "text-amber-300";
}

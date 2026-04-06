export type FindingConfidenceLevel = "high" | "medium" | "low";

/** Normalize backend or legacy values to a confidence tier for key findings. */
export function normalizeFindingConfidence(v: unknown): FindingConfidenceLevel {
  const s = String(v ?? "").toLowerCase().trim();
  if (s === "high" || s === "h") return "high";
  if (s === "low" || s === "l") return "low";
  return "medium";
}

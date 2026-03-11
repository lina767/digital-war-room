/**
 * Actors in the Iran conflict (aligned with conflicts.app style).
 * Activity and intelligence come from backend analysis when available.
 */

export type ActorRole = "aggressor" | "retaliating" | "defender" | "neutral";

export interface ActorIntelligence {
  official_position?: string;
  verified_actions?: string[];
  signals?: string[];
  military_profile?: string;
}

export interface ConflictActor {
  id: string;
  name: string;
  role: ActorRole;
  /** 0–100, from analysis or heuristic */
  activity: number;
  /** Optional: multiplier/count from intel (e.g. x79) */
  value_label?: string;
  intelligence?: ActorIntelligence;
}

/** Iran conflict: default actor list (roles from open-source reporting). Activity filled by backend or frontend heuristic. */
export const IRAN_CONFLICT_ACTORS: Omit<ConflictActor, "activity" | "intelligence">[] = [
  { id: "israel", name: "Israel", role: "aggressor", value_label: "x79" },
  { id: "united_states", name: "United States", role: "aggressor", value_label: "x104" },
  { id: "iran", name: "Iran", role: "retaliating", value_label: "x60" },
  { id: "irgc", name: "IRGC", role: "retaliating", value_label: "x19" },
  { id: "nato", name: "NATO", role: "defender", value_label: "x61" },
  { id: "hezbollah", name: "Hezbollah", role: "retaliating", value_label: "x10" },
  { id: "us_il_joint", name: "US–IL Joint", role: "aggressor", value_label: "x1" },
  { id: "russia", name: "Russia", role: "neutral", value_label: "x12" },
  { id: "houthis", name: "Houthis", role: "retaliating", value_label: "x2" },
  { id: "iraqi_pmf", name: "Iraqi PMF", role: "neutral", value_label: "x4" },
];

/** Compute activity 0–100 from key_findings: count mentions of actor name (or id) in findings. */
export function activityFromKeyFindings(
  actorId: string,
  actorName: string,
  keyFindings: string[] = []
): number {
  const text = keyFindings.join(" ").toLowerCase();
  const terms: string[] = [];
  if (actorId === "us_il_joint") terms.push("us", "israel", "joint", "strike");
  else if (actorId === "irgc") terms.push("irgc", "revolutionary guard");
  else if (actorId === "iraqi_pmf") terms.push("pmf", "iraqi", "popular mobilization");
  else terms.push(actorName.toLowerCase(), actorId.replace(/_/g, " "));
  const count = terms.filter((t) => text.includes(t)).length;
  if (count === 0) return 40; // baseline
  return Math.min(100, 40 + count * 15);
}

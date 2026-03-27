export type ConflictTier = "tier1" | "tier2" | "tier3";

export interface ConflictReadiness {
  conflict: string;
  tier: ConflictTier;
  signalDensity: number;
  dataQuality: number;
  userDemand: number;
  strategicImpact: number;
  score: number;
}

function weightedScore(signalDensity: number, dataQuality: number, userDemand: number, strategicImpact: number): number {
  const raw = signalDensity * 0.3 + dataQuality * 0.25 + userDemand * 0.2 + strategicImpact * 0.25;
  return Math.round(raw);
}

function makeReadiness(
  conflict: string,
  tier: ConflictTier,
  signalDensity: number,
  dataQuality: number,
  userDemand: number,
  strategicImpact: number
): ConflictReadiness {
  return {
    conflict,
    tier,
    signalDensity,
    dataQuality,
    userDemand,
    strategicImpact,
    score: weightedScore(signalDensity, dataQuality, userDemand, strategicImpact),
  };
}

export const CONFLICT_READINESS: ConflictReadiness[] = [
  makeReadiness("Middle East", "tier1", 92, 88, 90, 95),
  makeReadiness("Ukraine", "tier1", 90, 86, 91, 92),
  makeReadiness("Red Sea and Horn of Africa", "tier1", 88, 83, 85, 93),
  makeReadiness("Taiwan Strait", "tier1", 82, 79, 80, 91),
  makeReadiness("Sahel", "tier2", 76, 70, 73, 78),
  makeReadiness("Sudan", "tier2", 74, 72, 70, 76),
  makeReadiness("DRC", "tier2", 68, 67, 64, 71),
  makeReadiness("Myanmar", "tier2", 66, 65, 63, 72),
  makeReadiness("Korean Peninsula", "tier3", 62, 68, 58, 74),
];

/** Dashboard theater selector is Middle East–only; all listed conflicts are treated as core. */
export const CORE_THEATERS = ["Middle East", "Iran", "Lebanon"] as const;

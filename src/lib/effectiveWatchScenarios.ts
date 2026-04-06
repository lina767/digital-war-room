import type { ConflictData } from "@/types/conflict";

function hasScenarioDescription(
  scenario: ConflictData["scenarios"] extends Array<infer T> ? T : never,
): scenario is NonNullable<ConflictData["scenarios"]>[number] {
  return Boolean(
    scenario && typeof scenario.description === "string" && scenario.description.trim().length > 0,
  );
}

export function toScenarioProbabilityPercent(probability: number | null | undefined): number | null {
  if (typeof probability !== "number" || !Number.isFinite(probability)) return null;
  const normalized = probability <= 1 ? probability * 100 : probability;
  return Math.round(Math.max(0, Math.min(100, normalized)));
}

/**
 * When the API returns no supervisor scenarios, still show actionable "Things to Watch"
 * items derived from conflict label and escalation score (rough emphasis only).
 */
export function effectiveWatchScenarios(
  conflictLabel: string | undefined,
  escalationScore: number | undefined,
  apiScenarios: ConflictData["scenarios"] | undefined | null,
): NonNullable<ConflictData["scenarios"]> {
  const fromApi = (apiScenarios ?? []).filter(hasScenarioDescription);
  if (fromApi.length > 0) return fromApi;

  const label = (conflictLabel || "this theater").trim();
  const esc = Math.max(0, Math.min(100, Math.round(Number(escalationScore ?? 50))));
  const escBias = (esc - 50) / 100;
  const pEsc = Math.min(0.42, Math.max(0.18, 0.28 + escBias * 0.2));
  const pStable = Math.min(0.4, Math.max(0.2, 0.32 - escBias * 0.12));

  return [
    {
      description: `Pattern hold for ${label}: treat material change as a signal when SIGINT posture, NEWS throughput, and FININT (e.g. Brent) move together rather than in isolation.`,
      probability: pStable,
    },
    {
      description: `Escalation corridor: watch for correlated spikes—military/transport indicators, headline density, and commodity stress—before updating your prior on ${label}.`,
      probability: pEsc,
    },
    {
      description:
        "Maritime and chokepoints: cross-check tanker/AIS context, disruption language in coverage, and ENERGY readings when reassessing spillover risk.",
      probability: 0.22,
    },
    {
      description:
        "Tail risks: diplomatic shocks or single-point failures may lag in OSINT; keep a slot for late-breaking sources and primary corroboration.",
      probability: 0.14,
    },
  ];
}

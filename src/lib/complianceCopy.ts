/**
 * Single source of truth for Sanctions Compliance UI copy (Panel + Daily Briefing).
 * English. Use for intro, disclaimer, match/risk level explanations, and glossary.
 */

export const COMPLIANCE_INTRO_SHORT =
  "Conflict-level compliance risk from sanctions lists (OFAC/EU), geofencing, and AIS signals. " +
  "Supports due diligence; not legal advice.";

export const COMPLIANCE_INTRO_FULL =
  "This panel shows a compliance risk score (LOW–CRITICAL) based on: conflict sanctions regime, OFAC SDN and EU list coverage, " +
  "geofencing (assets in sanctions zones), AIS anomalies (spoofing/dark activity), and escalation context. " +
  "The score is indicative; use the search below to check specific entities. " +
  "Geofencing and AIS sections show real-time exposure when SIGINT data falls inside configured zones. " +
  "Intelligence signals only – not legal advice.";

export const COMPLIANCE_DISCLAIMER =
  "Intelligence signals only – not legal advice. Supports due diligence but does not replace legal review.";

/** User-facing explanations for each sanctions match level (for tooltips/badges). */
export const MATCH_LEVEL_LABELS: Record<string, string> = {
  EXACT: "Exact list match – name matches sanctioned entity directly.",
  STRONG_FUZZY: "Strong fuzzy match – high similarity, likely same entity (e.g. spelling/transliteration).",
  WEAK_FUZZY: "Weak fuzzy match – moderate similarity; manual review recommended.",
  REVIEW: "Low similarity – flagged for review only; verify manually.",
};

/** User-facing explanations for risk levels. */
export const RISK_LEVEL_LABELS: Record<string, string> = {
  CRITICAL: "Direct list hit or very high exposure.",
  HIGH: "Comprehensive regime or significant list/zone exposure.",
  MEDIUM: "Moderate list or zone exposure.",
  LOW: "Few or no compliance signals.",
};

/** Key terms for glossary / tooltips (term -> short definition). */
export const COMPLIANCE_GLOSSARY: Array<{ term: string; definition: string }> = [
  { term: "OFAC", definition: "US Treasury Office of Foreign Assets Control; administers sanctions lists." },
  { term: "SDN", definition: "Specially Designated Nationals list; OFAC list of sanctioned entities and vessels." },
  { term: "EU Consolidated List", definition: "EU sanctions list (persons, entities, vessels)." },
  { term: "Geofencing", definition: "Alerts when tracked assets (ships/aircraft) are inside configured sanctions zones." },
  { term: "AIS anomaly", definition: "Behavioral flag (e.g. spoofing, dark activity) from AIS position data." },
  { term: "Band", definition: "Rough probability range for the risk level; not a precise forecast." },
];

/** Shown when there are no geofencing or AIS alerts. */
export const COMPLIANCE_NO_ALERTS_TEXT =
  "Alerts appear only when SIGINT positions (ships/aircraft) fall inside sanctions zones or AIS anomalies are detected. " +
  "If there are no hits or no SIGINT data for the region, this list stays empty. " +
  "Dark-activity detection requires at least two consecutive analysis runs.";

export const LISTS_COVERED_NOTE =
  "Lists covered: OFAC SDN, EU Consolidated. UN, UK OFSI, Swiss SECO not yet integrated.";

// ─── Document QA (Ask about sanctions documents) ───────────────────────────

export const DOC_QA_INTRO =
  "Ask a question about the current compliance context: risk level, OFAC SDN sample and programs, and recent Treasury actions. " +
  "Answers are based only on the data from this run (no PDF or list search).";

export const DOC_QA_PLACEHOLDER =
  "e.g. Which OFAC programs are most relevant? Summarise the risk drivers.";

export const DOC_QA_DISCLAIMER =
  "Answers are based only on the compliance context from this run. Intelligence signals – not legal advice.";

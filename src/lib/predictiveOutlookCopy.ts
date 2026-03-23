/**
 * Shared copy for Predictive Outlook (Panel + Daily Intelligence Briefing).
 * English; single source for intro and disclaimer.
 */

export const PREDICTIVE_OUTLOOK_INTRO =
  "Estimates escalation for the next 24h (and 7d) by comparing a conflict baseline with current agent scores. " +
  "The baseline is the level you’d expect if there were no new signals (\"null hypothesis\"). " +
  "The 24h/7d level emphasises the strongest agent signals so a few critical domains are not diluted by quieter ones. " +
  "Bands are rough probability ranges, not precise forecasts.";

export const PREDICTIVE_OUTLOOK_INTRO_SHORT =
  "Compares a conflict baseline (expected level without new signals) with current agent scores for 24h and 7d. " +
  "Strong signals from key agents drive the level; bands are rough ranges, not precise probabilities.";

export const PREDICTIVE_OUTLOOK_DISCLAIMER =
  "Levels and bands are coarse indicators from agent scores and a conflict-specific baseline–not precise probabilities.";

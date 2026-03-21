/**
 * Shared copy for Intelligence Feed panel "What is this?" tooltips.
 * One entry per panel so every section can explain what it shows and how to interpret it.
 */

export const DASHBOARD_PANEL_TOOLTIPS: Record<string, string> = {
  "UPDATED BRIEFING":
    "Recap and scenarios from the latest multi-agent run. Summary, key findings, likely driver hypotheses (signal → plausible cause), and things to watch are synthesized by the supervisor from all stream results.",
  "SIGNAL FRAMEWORK":
    "State vs. exile/independent media comparison (e.g. IRNA/Fars vs Iran International). Synthesis and consistency score help assess narrative divergence and information vacuum.",
  "PREDICTIVE OUTLOOK":
    "Escalation and market outlook from the supervisor. Levels (LOW to CRITICAL) and confidence reflect agent inputs; drivers explain what is pushing the assessment.",
  "SANCTIONS COMPLIANCE":
    "Conflict-level compliance risk from sanctions lists (OFAC/EU), geofencing, and AIS signals. Score is indicative; use the search to check specific entities. Not legal advice.",
  "CHOKEPOINT MONITOR":
    "Status of key maritime and supply chokepoints (e.g. Strait of Hormuz). Red/amber/green reflect disruption risk. Asterisk (*) means manual override.",
  "GLOBAL IMPACT":
    "When available: oil/Hormuz risk and supply-chain implications from ENERGY and key findings. Shown when the conflict (e.g. Iran) has material global impact signals.",
  "LATEST HEADLINES":
    "News articles for the selected conflict from NewsAPI, RSS, and other sources. Headlines and sentiment feed into the news score and supervisor synthesis.",
  "EVENTS TIMELINE":
    "Key findings from the latest run, filterable by category (conflict, diplomacy, economy, tech). One line per finding; order reflects salience.",
  "PROXIMITY ANALYZER":
    "Strike–civilian correlation: NASA FIRMS thermal anomalies vs. OSM schools/hospitals within 300 m. Human-shield/collateral risk labels; evidence list for key findings.",
  "ACTIVITY & CONNECTIVITY":
    "GreyNoise cyber context, news sentiment, internet connectivity (IODA), SIGINT tracker (ADS-B), and prediction markets. Activity and connectivity signals in one place.",
};

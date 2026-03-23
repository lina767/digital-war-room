/** Static marketing landing copy (English). Kept in TS for reuse; root page is plain HTML + this for future i18n. */
export const LANDING = {
  headline: "Open-source noise is not a strategy.",
  subhead:
    "Analysts and editors drown in feeds while escalation moves in hours. Digital War Room fuses GEOINT, SIGINT, SOCMINT, FININT, TECHINT, CYBER, NEWS, DIPLO, ENERGY, PROTEST, PROXIMITY, and related streams into one escalation score and BLUF-style briefings—so you see the pattern before the headline.",
  primaryCta: "View curated demo",
  primaryCtaHref: "/demo",
  secondaryCta: "Open live dashboard",
  secondaryCtaHref: "/app/dashboard",
  waitlistCta: "Newsletter",
  waitlistHref: "/newsletter",
  useCases: [
    {
      title: "Geopolitical & security analysis",
      body: "Track chokepoints, military posture, and corroborated patterns across agents–without tab bankruptcy.",
      imageAlt: "Escalation and multi-stream intelligence overview",
    },
    {
      title: "Editorial & investigations",
      body: "Turn OSINT into defensible narratives: scores, timelines, and source transparency for fast fact-checking.",
      imageAlt: "Briefing-style summary and key findings",
    },
    {
      title: "Markets & risk",
      body: "See how conflict signals connect to energy, logistics, and sentiment–before volatility shows up in headlines.",
      imageAlt: "Markets and escalation context",
    },
  ],
  socialProof:
    "Built in public on GitHub. Designed for analysts who need signal, not another dashboard full of charts.",
  githubHref: "https://github.com/lina767/digital-war-room",
} as const;

import { PINNED_ONE_LINER } from "@/lib/seoCopy";

/** Static marketing landing copy (English). Kept in TS for reuse; root page is plain HTML + this for future i18n. */
export const LANDING = {
  /** Canonical pinned narrative — same as `PINNED_ONE_LINER` in seoCopy.ts */
  oneLiner: PINNED_ONE_LINER,
  /** Short line under the logo / in meta titles */
  tagline: "AI-native OSINT, built in public",
  headline: "Open-source noise is not a strategy.",
  subhead:
    "Analysts and editors drown in feeds while escalation moves in hours. Digital War Room fuses GEOINT, SIGINT, SOCMINT, FININT, TECHINT, CYBER, NEWS, DIPLO, ENERGY, PROXIMITY, and related streams into one escalation score and BLUF-style briefings—so you see the pattern before the headline. Not a finished enterprise product: a serious pipeline you can follow, fork, and challenge.",
  primaryCta: "Open live dashboard",
  primaryCtaHref: "/app/dashboard",
  secondaryCta: "View curated demo",
  secondaryCtaHref: "/demo",
  dailyBriefingCta: "Daily briefing",
  dailyBriefingHref: "/daily-briefing",
  attentionPlaybookCta: "Attention playbook (docs)",
  attentionPlaybookHref: "/docs/documentation?doc=attention-playbook",
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
    "Built in public on GitHub. Start on the live dashboard, then daily briefing and docs—signal and methodology over hype.",
  githubHref: "https://github.com/lina767/digital-war-room",
} as const;

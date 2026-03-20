export interface DocumentationLinkItem {
  label: string;
  description?: string;
  to?: string;
  href?: string;
  external?: boolean;
}

export interface DocumentationSection {
  heading: string;
  description?: string;
  items: DocumentationLinkItem[];
}

const REPO_DOCS_BASE = "https://github.com/lina767/digital-war-room/blob/main/docs";

export const CANONICAL_DOC_LINKS = {
  projectDocumentation: `${REPO_DOCS_BASE}/PROJECT-DOCUMENTATION.md`,
  architecture: `${REPO_DOCS_BASE}/ARCHITECTURE.md`,
  apiReference: `${REPO_DOCS_BASE}/API-REFERENCE.md`,
  deployment: `${REPO_DOCS_BASE}/DEPLOYMENT.md`,
  howItWorks: `${REPO_DOCS_BASE}/how-it-works.md`,
  methodology: `${REPO_DOCS_BASE}/methodology.md`,
  sourceDirectory: `${REPO_DOCS_BASE}/source-directory.md`,
} as const;

export const DOCUMENTATION_SECTIONS: DocumentationSection[] = [
  {
    heading: "Platform Overview",
    description: "Start here if you are new to the project or want a high-level understanding.",
    items: [
      {
        label: "Complete Project Documentation",
        description: "Single, end-to-end technical documentation for architecture, setup, API, and operations.",
        href: CANONICAL_DOC_LINKS.projectDocumentation,
        external: true,
      },
      {
        label: "README",
        description: "Product overview, architecture snapshot, and quick start instructions.",
        href: "https://github.com/lina767/digital-war-room#readme",
        external: true,
      },
      {
        label: "How It Works",
        description: "User-facing explanation of dashboard flow, intelligence fusion, and platform logic.",
        to: "/how-it-works",
      },
    ],
  },
  {
    heading: "Architecture and Agents",
    description: "Understand backend layers, orchestration, and how specialized agents contribute.",
    items: [
      {
        label: "Architecture",
        description: "Backend layer model, dependency rules, and execution path.",
        href: CANONICAL_DOC_LINKS.architecture,
        external: true,
      },
      {
        label: "Agent Catalog",
        description: "Per-agent inputs, data sources, outputs, and usage context.",
        href: "https://github.com/lina767/digital-war-room/blob/main/docs/AGENTS.md",
        external: true,
      },
      {
        label: "Agent Tool Chain",
        description: "Rule-based collection pipeline and model/tool coordination by agent.",
        href: "https://github.com/lina767/digital-war-room/blob/main/docs/AGENT-TOOL-CHAIN.md",
        external: true,
      },
      {
        label: "Methodology",
        description: "Escalation scoring rationale, weighting logic, and analytical framework.",
        to: "/methodology",
      },
    ],
  },
  {
    heading: "API and Integrations",
    description: "Backend endpoints, real-time channels, and external service integration points.",
    items: [
      {
        label: "API Reference",
        description: "REST endpoints for analysis, monitoring, compliance, documents, and newsletter.",
        href: CANONICAL_DOC_LINKS.apiReference,
        external: true,
      },
      {
        label: "API Keys and Providers",
        description: "Required and optional keys for LLMs, data providers, and enrichment features.",
        href: "https://github.com/lina767/digital-war-room/blob/main/docs/API-KEYS.md",
        external: true,
      },
      {
        label: "Source Directory",
        description: "Transparent mapping of intelligence sources and reliability notes.",
        to: "/sources",
      },
      {
        label: "Agent Monitor",
        description: "Operational view of latest per-agent status and health signals.",
        to: "/app/monitoring",
      },
    ],
  },
  {
    heading: "Operations and Deployment",
    description: "Runbook content for local development, production rollout, and maintenance.",
    items: [
      {
        label: "Deployment Guide",
        description: "Vercel and Railway setup with environment and go-live checklist.",
        href: CANONICAL_DOC_LINKS.deployment,
        external: true,
      },
      {
        label: "Docker Development",
        description: "Compose-based local stack with frontend, backend, and pgvector database.",
        href: "https://github.com/lina767/digital-war-room/blob/main/docs/DOCKER-DEV.md",
        external: true,
      },
      {
        label: "Observability",
        description: "Sentry, OpenTelemetry, and operational logging guidance.",
        href: "https://github.com/lina767/digital-war-room/blob/main/docs/OBSERVABILITY.md",
        external: true,
      },
      {
        label: "Security",
        description: "Production hardening recommendations and safe configuration guidance.",
        href: "https://github.com/lina767/digital-war-room/blob/main/docs/SECURITY.md",
        external: true,
      },
      {
        label: "Contributing",
        description: "Contribution workflow, quality checks, and project conventions.",
        href: "https://github.com/lina767/digital-war-room/blob/main/CONTRIBUTING.md",
        external: true,
      },
      {
        label: "Daily Briefing",
        description: "Briefing format and intelligence synthesis output used for daily updates.",
        to: "/daily-briefing",
      },
    ],
  },
  {
    heading: "Legal",
    description: "Compliance and legal pages for public use of the platform.",
    items: [
      { label: "Legal Notice", description: "Provider identification and legal notice page.", to: "/impressum" },
      { label: "Privacy Policy", description: "Privacy and data handling policy.", to: "/privacy" },
      {
        label: "License",
        description: "Repository license terms.",
        href: "https://github.com/lina767/digital-war-room/blob/main/LICENSE",
        external: true,
      },
    ],
  },
];

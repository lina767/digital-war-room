import projectDocumentation from "../../docs/PROJECT-DOCUMENTATION.md?raw";
import architecture from "../../docs/ARCHITECTURE.md?raw";
import apiReference from "../../docs/API-REFERENCE.md?raw";
import deployment from "../../docs/DEPLOYMENT.md?raw";
import agents from "../../docs/AGENTS.md?raw";
import agentToolChain from "../../docs/AGENT-TOOL-CHAIN.md?raw";
import methodology from "../../docs/methodology.md?raw";
import howItWorks from "../../docs/how-it-works.md?raw";
import sourceDirectory from "../../docs/source-directory.md?raw";
import observability from "../../docs/OBSERVABILITY.md?raw";
import security from "../../docs/SECURITY.md?raw";
import apiKeys from "../../docs/API-KEYS.md?raw";
import newsletterSpec from "../../docs/NEWSLETTER-SPEC.md?raw";

const REPO_DOCS_BASE = "https://github.com/lina767/digital-war-room/blob/main/docs";

export const CANONICAL_DOC_LINKS = {
  projectDocumentation: `${REPO_DOCS_BASE}/PROJECT-DOCUMENTATION.md`,
  architecture: `${REPO_DOCS_BASE}/ARCHITECTURE.md`,
  apiReference: `${REPO_DOCS_BASE}/API-REFERENCE.md`,
  deployment: `${REPO_DOCS_BASE}/DEPLOYMENT.md`,
  howItWorks: `${REPO_DOCS_BASE}/how-it-works.md`,
  methodology: `${REPO_DOCS_BASE}/methodology.md`,
  sourceDirectory: `${REPO_DOCS_BASE}/source-directory.md`,
  security: `${REPO_DOCS_BASE}/SECURITY.md`,
  observability: `${REPO_DOCS_BASE}/OBSERVABILITY.md`,
} as const;

export interface DocumentationManifestSection {
  id: string;
  title: string;
  description: string;
}

export interface DocumentationManifestDoc {
  id: string;
  sectionId: string;
  title: string;
  description: string;
  filePath: string;
  githubUrl: string;
  content: string;
}

export const DEFAULT_DOC_ID = "project-documentation";

export const DOCUMENTATION_MANIFEST_SECTIONS: DocumentationManifestSection[] = [
  {
    id: "overview",
    title: "Overview",
    description: "Project orientation, product context, and the main technical entry points.",
  },
  {
    id: "architecture",
    title: "Architecture",
    description: "Backend layers, orchestration model, and agent system design.",
  },
  {
    id: "api-and-data",
    title: "API and Data",
    description: "Endpoints, provider setup, and source transparency.",
  },
  {
    id: "operations",
    title: "Operations",
    description: "Deployment runbooks, observability, and production hardening.",
  },
];

export const DOCUMENTATION_MANIFEST_DOCS: DocumentationManifestDoc[] = [
  {
    id: "project-documentation",
    sectionId: "overview",
    title: "Project Documentation",
    description: "Complete technical documentation for setup, architecture, API, and operations.",
    filePath: "docs/PROJECT-DOCUMENTATION.md",
    githubUrl: `${REPO_DOCS_BASE}/PROJECT-DOCUMENTATION.md`,
    content: projectDocumentation,
  },
  {
    id: "how-it-works",
    sectionId: "overview",
    title: "How It Works",
    description: "Conceptual explanation of product behavior and analytical pipeline.",
    filePath: "docs/how-it-works.md",
    githubUrl: `${REPO_DOCS_BASE}/how-it-works.md`,
    content: howItWorks,
  },
  {
    id: "architecture",
    sectionId: "architecture",
    title: "Architecture",
    description: "Layer boundaries, dependency rules, and execution path.",
    filePath: "docs/ARCHITECTURE.md",
    githubUrl: `${REPO_DOCS_BASE}/ARCHITECTURE.md`,
    content: architecture,
  },
  {
    id: "agents",
    sectionId: "architecture",
    title: "Agents",
    description: "Agent-by-agent overview of inputs, sources, and output fields.",
    filePath: "docs/AGENTS.md",
    githubUrl: `${REPO_DOCS_BASE}/AGENTS.md`,
    content: agents,
  },
  {
    id: "agent-tool-chain",
    sectionId: "architecture",
    title: "Agent Tool Chain",
    description: "Rule-based collection and model/tool usage across agent workflows.",
    filePath: "docs/AGENT-TOOL-CHAIN.md",
    githubUrl: `${REPO_DOCS_BASE}/AGENT-TOOL-CHAIN.md`,
    content: agentToolChain,
  },
  {
    id: "methodology",
    sectionId: "architecture",
    title: "Methodology",
    description: "Scoring weights, threat thresholds, peak-weighted escalation, and Signal Framework notes.",
    filePath: "docs/methodology.md",
    githubUrl: `${REPO_DOCS_BASE}/methodology.md`,
    content: methodology,
  },
  {
    id: "api-reference",
    sectionId: "api-and-data",
    title: "API Reference",
    description: "REST, streaming, and websocket endpoints exposed by the backend.",
    filePath: "docs/API-REFERENCE.md",
    githubUrl: `${REPO_DOCS_BASE}/API-REFERENCE.md`,
    content: apiReference,
  },
  {
    id: "api-keys",
    sectionId: "api-and-data",
    title: "API Keys",
    description: "Environment variable contract and external provider key setup.",
    filePath: "docs/API-KEYS.md",
    githubUrl: `${REPO_DOCS_BASE}/API-KEYS.md`,
    content: apiKeys,
  },
  {
    id: "source-directory",
    sectionId: "api-and-data",
    title: "Source Directory",
    description: "Provider inventory plus embedded searchable source list.",
    filePath: "docs/source-directory.md",
    githubUrl: `${REPO_DOCS_BASE}/source-directory.md`,
    content: sourceDirectory,
  },
  {
    id: "deployment",
    sectionId: "operations",
    title: "Deployment",
    description: "Production deployment guide for Railway + Vercel.",
    filePath: "docs/DEPLOYMENT.md",
    githubUrl: `${REPO_DOCS_BASE}/DEPLOYMENT.md`,
    content: deployment,
  },
  {
    id: "newsletter",
    sectionId: "operations",
    title: "Newsletter Spec",
    description: "Daily briefing newsletter flow, endpoints, and integration details.",
    filePath: "docs/NEWSLETTER-SPEC.md",
    githubUrl: `${REPO_DOCS_BASE}/NEWSLETTER-SPEC.md`,
    content: newsletterSpec,
  },
  {
    id: "observability",
    sectionId: "operations",
    title: "Observability",
    description: "Tracing, logs, monitoring setup, and diagnostics.",
    filePath: "docs/OBSERVABILITY.md",
    githubUrl: `${REPO_DOCS_BASE}/OBSERVABILITY.md`,
    content: observability,
  },
  {
    id: "security",
    sectionId: "operations",
    title: "Security",
    description: "Security posture, controls, and operational safeguards.",
    filePath: "docs/SECURITY.md",
    githubUrl: `${REPO_DOCS_BASE}/SECURITY.md`,
    content: security,
  },
];

export function getDocumentationDocById(id: string): DocumentationManifestDoc | undefined {
  return DOCUMENTATION_MANIFEST_DOCS.find((doc) => doc.id === id);
}

export function getDocumentationDocOrDefault(id: string | null | undefined): DocumentationManifestDoc {
  return getDocumentationDocById(id ?? "") ?? getDocumentationDocById(DEFAULT_DOC_ID) ?? DOCUMENTATION_MANIFEST_DOCS[0];
}

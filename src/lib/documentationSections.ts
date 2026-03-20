export interface DocumentationLinkItem {
  label: string;
  to?: string;
  href?: string;
  external?: boolean;
  featured?: boolean;
}

export interface DocumentationSection {
  heading: string;
  items: DocumentationLinkItem[];
}

const REPO_DOCS_BASE = "https://github.com/lina767/digital-war-room/blob/main/docs";

export const CANONICAL_DOC_LINKS = {
  howItWorks: `${REPO_DOCS_BASE}/how-it-works.md`,
  methodology: `${REPO_DOCS_BASE}/methodology.md`,
  sourceDirectory: `${REPO_DOCS_BASE}/source-directory.md`,
} as const;

export const DOCUMENTATION_SECTIONS: DocumentationSection[] = [
  {
    heading: "Getting Started",
    items: [
      { label: "Introduction", href: "https://digital-war-room.com/", featured: true },
      { label: "Getting Started", href: "https://github.com/lina767/digital-war-room#getting-started", external: true },
      { label: "Design Philosophy", to: "/how-it-works" },
    ],
  },
  {
    heading: "Platform & Features",
    items: [
      { label: "Platform Overview", to: "/how-it-works" },
      { label: "Features & Interface", to: "/how-it-works#dashboard-guide" },
      { label: "Hotspots & Navigation", to: "/how-it-works#dashboard-guide" },
    ],
  },
  {
    heading: "Intelligence & Analysis",
    items: [
      { label: "How it works", to: "/how-it-works" },
      { label: "Methodology", to: "/methodology" },
      { label: "Source directory", to: "/sources" },
      { label: "Daily Intelligence Briefing", to: "/daily-briefing" },
      { label: "Agent Monitor", to: "/app/monitoring" },
    ],
  },
  {
    heading: "Map Layers",
    items: [
      { label: "Map Engine", to: "/how-it-works#dashboard-guide" },
      { label: "Orbital Surveillance", to: "/sources" },
      { label: "Military Tracking", to: "/sources" },
      { label: "Maritime Intelligence", to: "/sources" },
      { label: "Natural Disaster Tracking", to: "/sources" },
      { label: "Infrastructure Cascade Analysis", to: "/sources" },
      { label: "Maps Infrastructure & Geocoding", to: "/sources" },
      { label: "Webcam Layer", to: "/sources" },
    ],
  },
  {
    heading: "Finance",
    items: [
      { label: "Finance & Market Data", to: "/sources" },
      { label: "Premium Finance", to: "/sources" },
      { label: "Premium Finance Search Layer", to: "/sources" },
    ],
  },
  {
    heading: "Desktop Application",
    items: [{ label: "Desktop Application", href: "https://github.com/lina767/digital-war-room/blob/main/docs/DEPLOYMENT.md", external: true }],
  },
  {
    heading: "Developer Guide",
    items: [
      { label: "Contributing", href: "https://github.com/lina767/digital-war-room/blob/main/CONTRIBUTING.md", external: true },
      { label: "Adding API Endpoints", href: "https://github.com/lina767/digital-war-room/blob/main/docs/API-REFERENCE.md", external: true },
      { label: "API Key Gating & Registration", href: "https://github.com/lina767/digital-war-room/blob/main/docs/API-KEYS.md", external: true },
      { label: "Deployment Guide", href: "https://github.com/lina767/digital-war-room/blob/main/docs/DEPLOYMENT.md", external: true },
      { label: "CORS", href: "https://github.com/lina767/digital-war-room/blob/main/backend/main.py#L85", external: true },
      { label: "Health Endpoints", href: "https://github.com/lina767/digital-war-room/blob/main/docs/API-REFERENCE.md", external: true },
      { label: "Data Sources", to: "/sources" },
    ],
  },
  {
    heading: "Legal",
    items: [
      { label: "License", to: "/impressum" },
      { label: "Privacy", to: "/privacy" },
    ],
  },
];

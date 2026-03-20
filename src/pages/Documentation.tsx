import { Link } from "react-router-dom";
import { ExternalLink, Files, BookOpen } from "lucide-react";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";
import { CANONICAL_DOC_LINKS, DOCUMENTATION_SECTIONS } from "@/lib/documentationSections";
import { TITLE_DOCUMENTATION, DESCRIPTION_DOCUMENTATION } from "@/lib/seoCopy";

function DocsLink({
  label,
  to,
  href,
  external,
  description,
}: {
  label: string;
  description?: string;
  to?: string;
  href?: string;
  external?: boolean;
}) {
  const baseClass =
    "group block rounded-xl border border-border bg-card/30 p-4 hover:bg-card/50 hover:border-primary/40 transition-colors";
  const labelClass = "text-base sm:text-lg font-medium text-foreground flex items-center gap-2";
  const descriptionClass = "mt-1 text-sm text-muted-foreground";

  if (to) {
    return (
      <Link to={to} className={baseClass}>
        <span className={labelClass}>{label}</span>
        {description && <p className={descriptionClass}>{description}</p>}
      </Link>
    );
  }

  if (href) {
    return (
      <a
        href={href}
        target={external ? "_blank" : undefined}
        rel={external ? "noopener noreferrer" : undefined}
        className={baseClass}
      >
        <span className={labelClass}>
          {label}
          {external && <ExternalLink className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />}
        </span>
        {description && <p className={descriptionClass}>{description}</p>}
      </a>
    );
  }

  return (
    <span className={baseClass}>
      <span className={labelClass}>{label}</span>
      {description && <p className={descriptionClass}>{description}</p>}
    </span>
  );
}

const Documentation = () => {
  return (
    <>
      <SEO
        title={TITLE_DOCUMENTATION}
        description={DESCRIPTION_DOCUMENTATION}
        path="/docs/documentation"
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Documentation", url: "https://digital-war-room.com/docs/documentation" },
        ]}
      />
      <ContentPageLayout
        label="DOCUMENTATION"
        title="Project Documentation"
        description={DESCRIPTION_DOCUMENTATION}
        icon={<Files className="h-5 w-5 text-muted-foreground" />}
        maxWidth="4xl"
      >
        <div className="space-y-10">
          <section className="rounded-xl border border-border bg-card/40 p-5 sm:p-6 space-y-3">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">Introduction</h2>
            <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
              Digital War Room is an AI-powered OSINT intelligence platform that fuses multi-domain signals into a single,
              operationally useful conflict picture. It combines specialized agents, real-time ingestion, and structured
              synthesis to help teams monitor escalation and act faster.
            </p>
          </section>

          <section className="rounded-xl border border-border bg-card/40 p-5 sm:p-6 space-y-3">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">What you can do</h2>
            <ul className="list-disc pl-5 space-y-1.5 text-sm sm:text-base text-muted-foreground">
              <li>Track conflict escalation in near real time across geopolitical theaters.</li>
              <li>Review fused outputs from intelligence domains such as GEOINT, SIGINT, SOCMINT, FININT, and CYBER.</li>
              <li>Inspect operational signals, anomalies, and source-backed findings in a single dashboard workflow.</li>
              <li>Use API endpoints for analysis, monitoring, compliance checks, document Q&amp;A, and exports.</li>
              <li>Run daily intelligence briefings and newsletter workflows for recurring stakeholder updates.</li>
              <li>Explore transparent source mappings, methodology, and deployment guidance for reproducible operations.</li>
            </ul>
          </section>

          <section className="rounded-xl border border-border bg-card/40 p-5 sm:p-6 space-y-3">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">Quick links</h2>
            <ul className="list-disc pl-5 space-y-1.5 text-sm sm:text-base text-muted-foreground">
              <li>
                <span className="font-semibold text-foreground">New here?</span>{" "}
                Start with{" "}
                <a
                  href="https://github.com/lina767/digital-war-room#getting-started"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  Getting Started
                </a>{" "}
                for installation and setup.
              </li>
              <li>
                <span className="font-semibold text-foreground">Want to understand the system?</span>{" "}
                Read{" "}
                <a
                  href={CANONICAL_DOC_LINKS.architecture}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  Architecture
                </a>{" "}
                for how the pieces fit together.
              </li>
              <li>
                <span className="font-semibold text-foreground">Looking for specific features?</span>{" "}
                See{" "}
                <Link to="/how-it-works" className="text-primary hover:underline">
                  Features &amp; Interface
                </Link>{" "}
                for the full capability list.
              </li>
              <li>
                <span className="font-semibold text-foreground">Interested in the data?</span>{" "}
                Check{" "}
                <Link to="/sources" className="text-primary hover:underline">
                  Data Sources
                </Link>{" "}
                for collection methods and source coverage.
              </li>
              <li>
                <span className="font-semibold text-foreground">Want to contribute?</span>{" "}
                Read{" "}
                <a
                  href="https://github.com/lina767/digital-war-room/blob/main/CONTRIBUTING.md"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  Contributing
                </a>{" "}
                for code style and PR process.
              </li>
              <li>
                <span className="font-semibold text-foreground">Building on the API?</span>{" "}
                Browse the{" "}
                <a
                  href={CANONICAL_DOC_LINKS.apiReference}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  API Reference
                </a>{" "}
                for implemented endpoints and payload guidance.
              </li>
            </ul>
          </section>

          <section className="rounded-xl border border-border bg-card/40 p-5 sm:p-6 space-y-2">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">License</h2>
            <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
              Digital War Room is released under the{" "}
              <a
                href="https://github.com/lina767/digital-war-room/blob/main/LICENSE"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                MIT License
              </a>
              .
            </p>
          </section>

          <section className="rounded-xl border border-border bg-card/40 p-5 sm:p-6 space-y-3">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">Built from your actual project setup</h2>
            <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
              This page is the curated entry point for Digital War Room documentation. It is aligned with the current codebase:
              FastAPI backend services, multi-agent intelligence orchestration, React dashboard routes, and production deployment
              workflow.
            </p>
          </section>

          <div className="space-y-10 sm:space-y-12">
            {DOCUMENTATION_SECTIONS.map((section) => (
              <section key={section.heading} className="space-y-4">
                <div className="space-y-1.5">
                  <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight">{section.heading}</h2>
                  {section.description && <p className="text-sm sm:text-base text-muted-foreground">{section.description}</p>}
                </div>
                <ul className="space-y-3.5 sm:space-y-4">
                  {section.items.map((item) => (
                    <li key={item.label}>
                      <DocsLink {...item} />
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>

          <section className="rounded-xl border border-border bg-card/40 p-4 sm:p-5 space-y-2">
            <p className="text-xs sm:text-sm text-muted-foreground">
              Canonical long-form docs in the repository:
            </p>
            <div className="flex flex-wrap gap-3 text-sm">
              <a
                href={CANONICAL_DOC_LINKS.projectDocumentation}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-primary hover:underline"
              >
                <BookOpen className="h-4 w-4" />
                PROJECT-DOCUMENTATION.md
              </a>
              <a
                href={CANONICAL_DOC_LINKS.architecture}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-primary hover:underline"
              >
                <BookOpen className="h-4 w-4" />
                ARCHITECTURE.md
              </a>
              <a
                href={CANONICAL_DOC_LINKS.apiReference}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-primary hover:underline"
              >
                <BookOpen className="h-4 w-4" />
                API-REFERENCE.md
              </a>
              <a
                href={CANONICAL_DOC_LINKS.howItWorks}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-primary hover:underline"
              >
                <BookOpen className="h-4 w-4" />
                how-it-works.md
              </a>
              <a
                href={CANONICAL_DOC_LINKS.methodology}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-primary hover:underline"
              >
                <BookOpen className="h-4 w-4" />
                methodology.md
              </a>
              <a
                href={CANONICAL_DOC_LINKS.sourceDirectory}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-primary hover:underline"
              >
                <BookOpen className="h-4 w-4" />
                source-directory.md
              </a>
              <a
                href={CANONICAL_DOC_LINKS.deployment}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-primary hover:underline"
              >
                <BookOpen className="h-4 w-4" />
                DEPLOYMENT.md
              </a>
            </div>
          </section>
        </div>
      </ContentPageLayout>
    </>
  );
};

export default Documentation;

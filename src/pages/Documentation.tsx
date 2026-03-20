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
  featured,
}: {
  label: string;
  to?: string;
  href?: string;
  external?: boolean;
  featured?: boolean;
}) {
  const linkClass = featured
    ? "inline-flex rounded-xl bg-emerald-100 dark:bg-emerald-900/30 px-4 py-1.5 text-[30px] sm:text-[32px] font-semibold text-emerald-600 dark:text-emerald-300"
    : "text-[30px] sm:text-[32px] text-foreground/85 hover:text-foreground transition-colors";

  if (to) {
    return (
      <Link to={to} className={linkClass}>
        {label}
      </Link>
    );
  }

  if (href) {
    return (
      <a
        href={href}
        target={external ? "_blank" : undefined}
        rel={external ? "noopener noreferrer" : undefined}
        className={`inline-flex items-center gap-2 ${linkClass}`}
      >
        <span>{label}</span>
        {external && <ExternalLink className="h-4 w-4 text-muted-foreground" />}
      </a>
    );
  }

  return <span className={featured ? linkClass : "text-[30px] sm:text-[32px] text-muted-foreground"}>{label}</span>;
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
        title="Documentation"
        description={DESCRIPTION_DOCUMENTATION}
        icon={<Files className="h-5 w-5 text-muted-foreground" />}
        maxWidth="4xl"
      >
        <div className="space-y-10">
          <div className="space-y-10 sm:space-y-12">
            {DOCUMENTATION_SECTIONS.map((section) => (
              <section key={section.heading} className="space-y-4">
                <h2 className="text-[34px] sm:text-[36px] font-semibold tracking-tight">{section.heading}</h2>
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
            </div>
          </section>
        </div>
      </ContentPageLayout>
    </>
  );
};

export default Documentation;

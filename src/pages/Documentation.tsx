import { useEffect } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { ExternalLink, Files } from "lucide-react";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";
import { DocsArticle, DocsToc } from "@/components/docs/DocsArticle";
import { DocsExportBar } from "@/components/docs/DocsExportBar";
import { DocsLayout } from "@/components/docs/DocsLayout";
import { DocsSidebar } from "@/components/docs/DocsSidebar";
import { SourceDirectoryDoc } from "@/components/docs/SourceDirectoryDoc";
import {
  DEFAULT_DOC_ID,
  DOCUMENTATION_MANIFEST_DOCS,
  DOCUMENTATION_MANIFEST_SECTIONS,
  documentationSeoPath,
  documentationSeoTitle,
  getDocumentationDocById,
  getDocumentationDocOrDefault,
} from "@/lib/documentationSections";
import { DESCRIPTION_DOCUMENTATION } from "@/lib/seoCopy";

const Documentation = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const requestedDocId = searchParams.get("doc");
  const activeDoc = getDocumentationDocOrDefault(requestedDocId);

  useEffect(() => {
    if (requestedDocId && !getDocumentationDocById(requestedDocId)) {
      setSearchParams({ doc: DEFAULT_DOC_ID }, { replace: true });
    }
  }, [requestedDocId, setSearchParams]);

  /** Deep links like `#how-to-read-the-dashboard` after markdown renders */
  useEffect(() => {
    const hash = location.hash?.replace(/^#/, "");
    if (!hash) return;
    const t = window.setTimeout(() => {
      document.getElementById(hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
    return () => window.clearTimeout(t);
  }, [location.hash, activeDoc.id, activeDoc.content]);

  const handleSelectDoc = (docId: string) => {
    setSearchParams({ doc: docId });
  };

  const seoPath = documentationSeoPath(activeDoc.id);
  const seoTitle = documentationSeoTitle(activeDoc.title);
  const seoDescription = activeDoc.description || DESCRIPTION_DOCUMENTATION;
  const site = "https://digital-war-room.com";
  const docBreadcrumbs = [
    { name: "Home", url: `${site}/` },
    { name: "Documentation", url: `${site}/docs/documentation` },
    { name: activeDoc.title, url: `${site}${seoPath}` },
  ];

  return (
    <>
      <SEO
        title={seoTitle}
        description={seoDescription}
        path={seoPath}
        breadcrumbs={docBreadcrumbs}
      />
      <ContentPageLayout
        label="DOCUMENTATION"
        title={activeDoc.title}
        description={seoDescription}
        icon={<Files className="h-5 w-5 text-muted-foreground" />}
        maxWidth="4xl"
        printHideNavigation
      >
        <style>{`
          @media print {
            @page { margin: 14mm; }
            .documentation-print-root {
              background: white !important;
              color: #111 !important;
            }
            .documentation-print-root .text-muted-foreground {
              color: #444 !important;
            }
            .documentation-print-root a {
              color: #0b57d0 !important;
              text-decoration: underline;
            }
            .documentation-print-root table,
            .documentation-print-root th,
            .documentation-print-root td {
              border-color: #ccc !important;
            }
            .documentation-print-root code {
              background: #f0f0f0 !important;
              color: #111 !important;
            }
            .documentation-print-root pre,
            .documentation-print-root code.block {
              background: #f5f5f5 !important;
              border: 1px solid #ccc !important;
            }
            .documentation-print-root h1,
            .documentation-print-root h2,
            .documentation-print-root h3 {
              break-after: avoid-page;
            }
          }
        `}</style>
        <div className="space-y-10">
          <DocsLayout
            sidebar={
              <DocsSidebar
                sections={DOCUMENTATION_MANIFEST_SECTIONS}
                docs={DOCUMENTATION_MANIFEST_DOCS}
                activeDocId={activeDoc.id}
                onSelectDoc={handleSelectDoc}
              />
            }
            article={
              <div className="documentation-print-root space-y-4">
                <section className="rounded-xl border border-border bg-card/25 p-4 sm:p-5 print:border-neutral-300 print:bg-white">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <h2 className="text-xl sm:text-2xl font-semibold tracking-tight print:hidden">{activeDoc.title}</h2>
                      <p className="text-sm text-muted-foreground mt-1">{activeDoc.description}</p>
                      <p className="text-xs text-muted-foreground mt-2">Source: {activeDoc.filePath}</p>
                    </div>
                    <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
                      <DocsExportBar doc={activeDoc} />
                      <a
                        href={activeDoc.githubUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center justify-center gap-1.5 text-xs text-primary hover:underline print:hidden"
                      >
                        View on GitHub
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </div>
                  </div>
                </section>
                <DocsArticle markdown={activeDoc.content} className="print:border-neutral-300 print:bg-white" />
                {activeDoc.id === "source-directory" && <SourceDirectoryDoc />}
              </div>
            }
            toc={<DocsToc markdown={activeDoc.content} />}
          />
        </div>
      </ContentPageLayout>
    </>
  );
};

export default Documentation;

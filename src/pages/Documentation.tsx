import { useEffect } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { ExternalLink, Files } from "lucide-react";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";
import { DocsArticle, DocsToc } from "@/components/docs/DocsArticle";
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
      >
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
              <div className="space-y-4">
                <section className="rounded-xl border border-border bg-card/25 p-4 sm:p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">{activeDoc.title}</h2>
                      <p className="text-sm text-muted-foreground mt-1">{activeDoc.description}</p>
                      <p className="text-xs text-muted-foreground mt-2">Source: {activeDoc.filePath}</p>
                    </div>
                    <a
                      href={activeDoc.githubUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline shrink-0"
                    >
                      View on GitHub
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </div>
                </section>
                <DocsArticle markdown={activeDoc.content} />
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

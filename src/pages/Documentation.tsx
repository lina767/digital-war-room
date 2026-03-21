import { useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ExternalLink, Files, MousePointerClick } from "lucide-react";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";
import { DocsArticle, DocsToc } from "@/components/docs/DocsArticle";
import { DocsLayout } from "@/components/docs/DocsLayout";
import { DocsSidebar } from "@/components/docs/DocsSidebar";
import {
  DEFAULT_DOC_ID,
  DOCUMENTATION_MANIFEST_DOCS,
  DOCUMENTATION_MANIFEST_SECTIONS,
  getDocumentationDocById,
  getDocumentationDocOrDefault,
} from "@/lib/documentationSections";
import { TITLE_DOCUMENTATION, DESCRIPTION_DOCUMENTATION } from "@/lib/seoCopy";

const Documentation = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedDocId = searchParams.get("doc");
  const activeDoc = getDocumentationDocOrDefault(requestedDocId);

  useEffect(() => {
    if (requestedDocId && !getDocumentationDocById(requestedDocId)) {
      setSearchParams({ doc: DEFAULT_DOC_ID }, { replace: true });
    }
  }, [requestedDocId, setSearchParams]);

  const handleSelectDoc = (docId: string) => {
    setSearchParams({ doc: docId });
  };

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
                {activeDoc.interactivePage && (
                  <section
                    className="rounded-xl border border-primary/30 bg-primary/5 p-4 sm:p-5"
                    aria-label="Interactive companion page"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                      <div className="flex gap-3 min-w-0">
                        <div className="mt-0.5 rounded-md border border-primary/25 bg-background/80 p-2 shrink-0">
                          <MousePointerClick className="h-5 w-5 text-primary" aria-hidden />
                        </div>
                        <div className="min-w-0">
                          <h3 className="text-sm font-semibold text-foreground tracking-tight">
                            Interactive page
                          </h3>
                          <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                            {activeDoc.interactivePage.description}
                          </p>
                          <p className="text-xs text-muted-foreground/90 mt-2 font-mono break-all">
                            {activeDoc.interactivePage.url}
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-col sm:items-end gap-2 shrink-0">
                        <a
                          href={activeDoc.interactivePage.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors min-h-11 sm:min-h-10"
                        >
                          {activeDoc.interactivePage.label}
                          <ExternalLink className="h-4 w-4 flex-shrink-0" />
                        </a>
                        {activeDoc.interactivePage.sameOriginPath && (
                          <Link
                            to={activeDoc.interactivePage.sameOriginPath}
                            className="text-xs text-primary hover:underline text-center sm:text-right"
                          >
                            Open in this app ({activeDoc.interactivePage.sameOriginPath})
                          </Link>
                        )}
                      </div>
                    </div>
                  </section>
                )}
                <DocsArticle markdown={activeDoc.content} />
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

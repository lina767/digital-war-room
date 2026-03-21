import { Button } from "@/components/ui/button";
import type { DocumentationManifestDoc, DocumentationManifestSection } from "@/lib/documentationSections";

interface DocsSidebarProps {
  sections: DocumentationManifestSection[];
  docs: DocumentationManifestDoc[];
  activeDocId: string;
  onSelectDoc: (docId: string) => void;
}

export function DocsSidebar({ sections, docs, activeDocId, onSelectDoc }: DocsSidebarProps) {
  return (
    <nav className="rounded-xl border border-border bg-card/30 p-4 space-y-5" aria-label="Documentation">
      {sections.map((section) => {
        const docsInSection = docs.filter((doc) => doc.sectionId === section.id);
        if (docsInSection.length === 0) return null;

        return (
          <section key={section.id} className="space-y-2.5">
            <div className="space-y-1">
              <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">{section.title}</h2>
              <p className="text-xs text-muted-foreground">{section.description}</p>
            </div>
            <ul className="space-y-1">
              {docsInSection.map((doc) => {
                const active = doc.id === activeDocId;
                return (
                  <li key={doc.id}>
                    <Button
                      type="button"
                      variant="ghost"
                      aria-current={active ? "page" : undefined}
                      className={`w-full justify-start h-auto px-2.5 py-2 rounded-md text-left ${
                        active ? "bg-primary/10 text-primary hover:bg-primary/15" : "text-foreground/90 hover:bg-muted/60"
                      }`}
                      onClick={() => onSelectDoc(doc.id)}
                    >
                      <span className="block leading-tight">
                        <span className="text-sm font-medium">{doc.title}</span>
                        <span className="block text-xs text-muted-foreground mt-0.5">{doc.filePath}</span>
                      </span>
                    </Button>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </nav>
  );
}

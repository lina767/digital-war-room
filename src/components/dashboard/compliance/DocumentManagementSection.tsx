import { useState } from "react";
import { FileText } from "lucide-react";
import { DEFAULT_CONFLICT } from "@/lib/conflictDefaults";
import { getDocuments, postDocumentsIngest, postDocumentsQa } from "@/lib/api";
import { CollapsibleSection } from "./shared";

export function DocumentManagementSection() {
  const [ingestUrl, setIngestUrl] = useState("");
  const [ingestConflict, setIngestConflict] = useState(DEFAULT_CONFLICT);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [docList, setDocList] = useState<Array<{ id?: string; url?: string; source?: string; conflict?: string }>>([]);
  const [listLoading, setListLoading] = useState(false);
  const [qaQuestion, setQaQuestion] = useState("");
  const [qaLoading, setQaLoading] = useState(false);
  const [qaResult, setQaResult] = useState<{ answer?: string; confidence?: number; sources?: string[] } | null>(null);

  async function handleIngest(e: React.FormEvent) {
    e.preventDefault();
    if (!ingestUrl.trim()) return;
    setIngestLoading(true);
    try {
      await postDocumentsIngest({
        url: ingestUrl.trim(),
        source: "pdf",
        conflict: ingestConflict.trim() || undefined,
      });
      setIngestUrl("");
      const list = await getDocuments();
      setDocList(list);
    } finally {
      setIngestLoading(false);
    }
  }

  async function handleList() {
    setListLoading(true);
    try {
      const list = await getDocuments();
      setDocList(list);
    } finally {
      setListLoading(false);
    }
  }

  async function handleDocQa(e: React.FormEvent) {
    e.preventDefault();
    if (!qaQuestion.trim()) return;
    setQaLoading(true);
    setQaResult(null);
    try {
      const data = await postDocumentsQa({
        question: qaQuestion.trim(),
        conflict: DEFAULT_CONFLICT,
      });
      setQaResult(data);
    } finally {
      setQaLoading(false);
    }
  }

  return (
    <CollapsibleSection
      icon={<FileText className="h-3 w-3 text-primary" />}
      label="DOCUMENT MANAGEMENT"
      count={1}
      defaultOpen={false}
    >
      <form onSubmit={handleIngest} className="space-y-1.5">
        <input
          type="url"
          placeholder="PDF URL to ingest"
          value={ingestUrl}
          onChange={(e) => setIngestUrl(e.target.value)}
          className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
        />
        <input
          type="text"
          placeholder="Conflict (optional)"
          value={ingestConflict}
          onChange={(e) => setIngestConflict(e.target.value)}
          className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
        />
        <div className="flex gap-2">
          <button type="submit" disabled={ingestLoading} className="rounded border border-border bg-primary/10 px-2 py-1 text-[11px]">
            {ingestLoading ? "Ingesting…" : "Ingest"}
          </button>
          <button type="button" onClick={handleList} disabled={listLoading} className="rounded border border-border px-2 py-1 text-[11px]">
            {listLoading ? "…" : "List docs"}
          </button>
        </div>
      </form>
      {docList.length > 0 && (
        <div className="text-[11px] text-muted-foreground">
          {docList.length} document(s): {docList.map((d) => d.id ?? d.url ?? "?").slice(0, 3).join(", ")}
          {docList.length > 3 ? "…" : ""}
        </div>
      )}
      <form onSubmit={handleDocQa} className="space-y-1.5 mt-2 pt-2 border-t border-border/50">
        <input
          type="text"
          placeholder="Question over ingested docs"
          value={qaQuestion}
          onChange={(e) => setQaQuestion(e.target.value)}
          className="w-full rounded border border-border bg-background px-2 py-1 text-[11px]"
        />
        <button type="submit" disabled={qaLoading} className="rounded border border-border bg-primary/10 px-2 py-1 text-[11px]">
          {qaLoading ? "…" : "QA"}
        </button>
      </form>
      {qaResult && (
        <div className="mt-1.5 rounded border border-border bg-background/50 px-2 py-1.5 text-[11px]">
          <p>{qaResult.answer ?? "-"}</p>
          {qaResult.confidence != null && <p className="text-muted-foreground">Confidence: {qaResult.confidence}</p>}
        </div>
      )}
    </CollapsibleSection>
  );
}

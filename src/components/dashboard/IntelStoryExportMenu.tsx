import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Download, FileJson, Link2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useIntelStoryExport } from "@/hooks/useIntelStoryExport";
import type { ConflictData } from "@/types/conflict";

interface Props {
  conflict: string;
  conflictData: ConflictData | null;
}

export function IntelStoryExportMenu({ conflict, conflictData }: Props) {
  const { exportPdf, exportJson, copyShareLink, buildSnapshot } = useIntelStoryExport();
  const [busy, setBusy] = useState(false);

  const run = async (kind: "pdf" | "json" | "link") => {
    const snapshot = buildSnapshot(conflict, conflictData);
    setBusy(true);
    try {
      if (kind === "pdf") await exportPdf(snapshot);
      else if (kind === "json") exportJson(snapshot);
      else {
        await copyShareLink(snapshot);
        toast.success("Share link copied to clipboard");
        return;
      }
      if (kind === "pdf") toast.success("PDF downloaded");
      if (kind === "json") toast.success("JSON downloaded");
    } catch (e) {
      console.error(e);
      toast.error("Export failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-0.5">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-9 px-2 font-mono text-[11px] border-border"
        disabled={busy}
        title="Export intel story as PDF"
        onClick={() => void run("pdf")}
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" aria-hidden />}
        <span className="hidden xl:inline ml-1">PDF</span>
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-9 px-2 font-mono text-[11px] border-border hidden sm:flex"
        disabled={busy}
        title="Export JSON"
        onClick={() => void run("json")}
      >
        <FileJson className="h-3.5 w-3.5" aria-hidden />
        <span className="hidden xl:inline ml-1">JSON</span>
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-9 px-2 font-mono text-[11px] border-border"
        disabled={busy}
        title="Copy share link (opens snapshot in hash)"
        onClick={() => void run("link")}
      >
        <Link2 className="h-3.5 w-3.5" aria-hidden />
        <span className="hidden xl:inline ml-1">Share</span>
      </Button>
    </div>
  );
}

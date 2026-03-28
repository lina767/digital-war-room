import { pdf } from "@react-pdf/renderer";
import { useCallback } from "react";
import { IntelStoryPdfDocument } from "@/features/intel-story/IntelStoryPdfDocument";
import { buildIntelStorySnapshot } from "@/features/intel-story/buildSnapshot";
import type { IntelStorySnapshot } from "@/features/intel-story/types";
import type { ConflictData } from "@/types/conflict";
import { buildIntelStoryShareUrl } from "@/features/intel-story/encodeShareLink";

function triggerJsonDownload(snapshot: IntelStorySnapshot) {
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `intel-story-${snapshot.conflict.replace(/[^a-z0-9-_]+/gi, "_")}-${snapshot.exportedAt.slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

export function useIntelStoryExport() {
  const exportPdf = useCallback(async (snapshot: IntelStorySnapshot) => {
    const blob = await pdf(<IntelStoryPdfDocument snapshot={snapshot} />).toBlob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `intel-story-${snapshot.conflict.replace(/[^a-z0-9-_]+/gi, "_")}-${snapshot.exportedAt.slice(0, 10)}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  }, []);

  const exportJson = useCallback((snapshot: IntelStorySnapshot) => {
    triggerJsonDownload(snapshot);
  }, []);

  const copyShareLink = useCallback(async (snapshot: IntelStorySnapshot) => {
    const url = buildIntelStoryShareUrl(snapshot);
    await navigator.clipboard.writeText(url);
    return url;
  }, []);

  const buildSnapshot = useCallback((conflict: string, data: ConflictData | null) => {
    return buildIntelStorySnapshot(conflict, data);
  }, []);

  return { exportPdf, exportJson, copyShareLink, buildSnapshot };
}

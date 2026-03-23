import { pdf } from "@react-pdf/renderer";
import { useCallback } from "react";
import { BriefingPdfDocument } from "@/features/daily-briefing/components/BriefingPdfDocument";
import type { DailyBriefingData } from "@/features/daily-briefing/types/briefing.types";

export function useBriefingExport() {
  return useCallback(async (data: DailyBriefingData) => {
    const blob = await pdf(<BriefingPdfDocument data={data} />).toBlob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `daily-briefing-${data.generatedAt.toISOString().slice(0, 10)}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  }, []);
}

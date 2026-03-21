import { FileDown, FileJson, Table } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { DocumentationManifestDoc } from "@/lib/documentationSections";
import {
  buildDocumentationCsv,
  buildDocumentationJson,
  documentationExportFilename,
  triggerTextDownload,
} from "@/lib/documentationExport";
import { cn } from "@/lib/utils";

interface DocsExportBarProps {
  doc: DocumentationManifestDoc;
  className?: string;
}

export function DocsExportBar({ doc, className }: DocsExportBarProps) {
  const handlePdf = () => {
    toast.message('Opening print dialog — choose "Save as PDF" as the destination.');
    window.print();
  };

  const handleJson = () => {
    const body = buildDocumentationJson(doc);
    triggerTextDownload(documentationExportFilename(doc, "json"), body, "application/json;charset=utf-8");
    toast.success("JSON file download started.");
  };

  const handleCsv = () => {
    const body = buildDocumentationCsv(doc);
    triggerTextDownload(documentationExportFilename(doc, "csv"), body, "text/csv;charset=utf-8");
    toast.success("CSV file download started.");
  };

  const btnClass = "gap-1.5 h-8 text-xs";

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-end gap-1.5 print:hidden",
        className,
      )}
      role="group"
      aria-label="Export documentation"
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <Button type="button" variant="outline" size="sm" className={btnClass} onClick={handlePdf} aria-label="Save as PDF via print dialog">
            <FileDown className="h-3.5 w-3.5 shrink-0" />
            PDF
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[240px] text-xs">
          Uses your browser print dialog — pick “Save as PDF” as the destination.
        </TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button type="button" variant="outline" size="sm" className={btnClass} onClick={handleJson} aria-label="Download JSON export">
            <FileJson className="h-3.5 w-3.5 shrink-0" />
            JSON
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[240px] text-xs">
          Full page: metadata, markdown body, and table of contents as structured JSON.
        </TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button type="button" variant="outline" size="sm" className={btnClass} onClick={handleCsv} aria-label="Download CSV export">
            <Table className="h-3.5 w-3.5 shrink-0" />
            CSV
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[240px] text-xs">
          Metadata and heading outline (UTF-8 with BOM for Excel).
        </TooltipContent>
      </Tooltip>
    </div>
  );
}

import type { DocumentationManifestDoc } from "@/lib/documentationSections";
import { extractToc } from "@/lib/documentationToc";

const EXPORT_VERSION = 1;
const CSV_BOM = "\uFEFF";

function csvEscapeCell(value: string): string {
  const t = String(value ?? "");
  if (/[",\n\r]/.test(t)) {
    return `"${t.replace(/"/g, '""')}"`;
  }
  return t;
}

function csvRow(cells: string[]): string {
  return cells.map(csvEscapeCell).join(",");
}

/** Stable download filename: `digital-war-room-doc-{id}-{date}.{ext}` */
export function documentationExportFilename(doc: DocumentationManifestDoc, ext: string): string {
  const day = new Date().toISOString().slice(0, 10);
  const safeId = doc.id.replace(/[^a-z0-9-]+/gi, "-").replace(/-+/g, "-").toLowerCase();
  return `digital-war-room-doc-${safeId}-${day}.${ext}`;
}

export function triggerTextDownload(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function buildDocumentationJson(doc: DocumentationManifestDoc): string {
  const exportedAt = new Date().toISOString();
  const toc = extractToc(doc.content);
  const payload = {
    exportVersion: EXPORT_VERSION,
    exportedAt,
    source: "Digital War Room — documentation",
    doc: {
      id: doc.id,
      title: doc.title,
      description: doc.description,
      filePath: doc.filePath,
      githubUrl: doc.githubUrl,
      markdown: doc.content,
    },
    tableOfContents: toc,
    notes:
      doc.id === "source-directory"
        ? "Markdown body only; the interactive Source Directory table on the site is not included in this file."
        : undefined,
  };
  return `${JSON.stringify(payload, null, 2)}\n`;
}

/** UTF-8 BOM + meta rows + TOC rows (Excel-friendly). */
export function buildDocumentationCsv(doc: DocumentationManifestDoc): string {
  const exportedAt = new Date().toISOString();
  const toc = extractToc(doc.content);
  const lines: string[] = [];
  lines.push(csvRow(["kind", "key", "level", "slug", "value"]));
  lines.push(csvRow(["meta", "id", "", "", doc.id]));
  lines.push(csvRow(["meta", "title", "", "", doc.title]));
  lines.push(csvRow(["meta", "description", "", "", doc.description]));
  lines.push(csvRow(["meta", "file_path", "", "", doc.filePath]));
  lines.push(csvRow(["meta", "github_url", "", "", doc.githubUrl]));
  lines.push(csvRow(["meta", "exported_at", "", "", exportedAt]));
  lines.push(csvRow(["meta", "markdown_chars", "", "", String(doc.content.length)]));
  lines.push(csvRow(["meta", "heading_count", "", "", String(toc.length)]));
  for (const item of toc) {
    lines.push(csvRow(["toc", "", String(item.level), item.slug, item.text]));
  }
  return `${CSV_BOM}${lines.join("\r\n")}\r\n`;
}

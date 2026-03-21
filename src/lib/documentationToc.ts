export interface TocItem {
  level: 2 | 3;
  text: string;
  slug: string;
}

export function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

/** Headings `##` / `###` only (matches in-page anchor slugs in DocsArticle). */
export function extractToc(markdown: string): TocItem[] {
  const lines = markdown.split("\n");
  const out: TocItem[] = [];
  const used = new Map<string, number>();

  for (const line of lines) {
    const h2 = line.match(/^##\s+(.+)$/);
    const h3 = line.match(/^###\s+(.+)$/);
    const target = h2 ?? h3;
    if (!target) continue;

    const level: 2 | 3 = h2 ? 2 : 3;
    const text = target[1].trim();
    const baseSlug = slugify(text);
    const count = used.get(baseSlug) ?? 0;
    used.set(baseSlug, count + 1);
    const slug = count === 0 ? baseSlug : `${baseSlug}-${count}`;
    out.push({ level, text, slug });
  }

  return out;
}

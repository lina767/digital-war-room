/** Normalize article source for stable keys and filtering. */
export function headlineSourceKey(source: string | undefined): string {
  const s = (source ?? "").trim();
  return s || "Unknown";
}

/** Distinct source keys from articles, sorted for stable UI. */
export function collectDistinctSourceKeys(sources: Array<{ source?: string }>): string[] {
  const set = new Set<string>();
  for (const a of sources) {
    set.add(headlineSourceKey(a.source));
  }
  return [...set].sort((a, b) => a.localeCompare(b));
}

/**
 * When `allowed` is empty, no filter (show all). When non-empty, only articles
 * whose normalized source is in the set.
 */
export function filterArticlesBySourceKeys<T extends { source?: string }>(
  articles: T[],
  allowed: Set<string>,
): T[] {
  if (allowed.size === 0) return articles;
  return articles.filter((a) => allowed.has(headlineSourceKey(a.source)));
}

/** Match common wire / major outlets by source label (case-insensitive). */
const MAJOR_WIRE_PATTERN =
  /reuters|bbc|associated press|ap news|\bap\b|\bafp\b|bloomberg|financial times|the guardian|guardian|wsj|wall street|economist|nytimes|new york times|washington post|politico|axios|al jazeera|euronews|deutsche welle|dw\.com|afp\.com/i;

export function filterKeysToMajorWires(keys: string[]): string[] {
  return keys.filter((k) => MAJOR_WIRE_PATTERN.test(k));
}

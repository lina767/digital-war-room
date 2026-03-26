import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

export const BASE_URL = "https://digital-war-room.com";

const DEFAULT_DOCUMENTATION_DOC_ID = "project-documentation";

/** Doc entry ids from DOCUMENTATION_MANIFEST_DOCS (must stay in sync with documentationSections.ts). */
function getDocumentationDocIds() {
  const documentationSectionsPath = join(__dirname, "..", "src", "lib", "documentationSections.ts");
  const source = readFileSync(documentationSectionsPath, "utf8");
  const start = source.indexOf("export const DOCUMENTATION_MANIFEST_DOCS");
  if (start === -1) {
    return [];
  }
  const end = source.indexOf("];", start);
  const block = source.slice(start, end);
  const docIdRegex = /\bid:\s*"([^"]+)"\s*,\s*sectionId:/g;
  const ids = [];
  let m = docIdRegex.exec(block);
  while (m) {
    ids.push(m[1]);
    m = docIdRegex.exec(block);
  }
  return ids;
}

function getDocumentationDeepLinkRoutes() {
  return getDocumentationDocIds()
    .filter((id) => id !== DEFAULT_DOCUMENTATION_DOC_ID)
    .map((id) => ({
      path: `/docs/documentation?doc=${encodeURIComponent(id)}`,
      changefreq: "monthly",
      priority: "0.65",
      prerender: true,
      sitemap: true,
    }));
}

const STATIC_PUBLIC_ROUTES = [
  // Root is static HTML (no Puppeteer); crawlers get full markup from index.html.
  { path: "/", changefreq: "daily", priority: "1.0", prerender: false, sitemap: true },
  // Demo loads curated JSON from API in the browser; prerender would only show loading state.
  { path: "/demo", changefreq: "weekly", priority: "0.95", prerender: false, sitemap: true },
  // Legacy URLs redirect client-side to /docs/documentation?doc=…; still prerender for crawlers.
  { path: "/how-it-works", changefreq: "monthly", priority: "0.5", prerender: true, sitemap: false },
  { path: "/methodology", changefreq: "monthly", priority: "0.5", prerender: true, sitemap: false },
  { path: "/sources", changefreq: "monthly", priority: "0.5", prerender: true, sitemap: false },
  { path: "/docs/documentation", changefreq: "monthly", priority: "0.85", prerender: true, sitemap: true },
  { path: "/docs", changefreq: "monthly", priority: "0.4", prerender: true, sitemap: false },
  { path: "/daily-briefing", changefreq: "daily", priority: "0.9", prerender: true, sitemap: true },
  { path: "/newsletter", changefreq: "weekly", priority: "0.6", prerender: true, sitemap: true },
  // Token pages are publicly routable for UX, but intentionally not listed in sitemap.
  { path: "/newsletter/confirm", changefreq: "never", priority: "0.1", prerender: true, sitemap: false },
  { path: "/newsletter/unsubscribe", changefreq: "never", priority: "0.1", prerender: true, sitemap: false },
  { path: "/impressum", changefreq: "yearly", priority: "0.3", prerender: true, sitemap: true },
  { path: "/privacy", changefreq: "yearly", priority: "0.3", prerender: true, sitemap: true },
  { path: "/support", changefreq: "monthly", priority: "0.5", prerender: true, sitemap: true },
  { path: "/blog", changefreq: "weekly", priority: "0.6", prerender: true, sitemap: true },
];

function getBlogPostSlugs() {
  const blogPostsPath = join(__dirname, "..", "src", "lib", "blogPosts.tsx");
  const source = readFileSync(blogPostsPath, "utf8");
  const slugRegex = /slug:\s*"([^"]+)"/g;
  const slugs = [];
  let match = slugRegex.exec(source);
  while (match) {
    if (match[1]) {
      slugs.push(match[1]);
    }
    match = slugRegex.exec(source);
  }
  return slugs;
}

function uniqueByPath(routes) {
  const seen = new Set();
  return routes.filter((route) => {
    if (seen.has(route.path)) {
      return false;
    }
    seen.add(route.path);
    return true;
  });
}

export function getDiscoverabilityRoutes() {
  const blogRoutes = getBlogPostSlugs().map((slug) => ({
    path: `/blog/${slug}`,
    changefreq: "monthly",
    priority: "0.5",
    prerender: true,
    sitemap: true,
  }));

  return uniqueByPath([...STATIC_PUBLIC_ROUTES, ...getDocumentationDeepLinkRoutes(), ...blogRoutes]);
}

export function getPrerenderRoutes() {
  // Query-string URLs (e.g. /docs/documentation?doc=...) are valid for discovery/sitemap
  // but not reliably handled by vite-plugin-seo-prerender output mapping.
  // Keep them discoverable, skip them for filesystem prerender generation.
  return getDiscoverabilityRoutes()
    .filter((r) => r.prerender && !r.path.includes("?"))
    .map((r) => r.path);
}

export function getSitemapRoutes() {
  return getDiscoverabilityRoutes().filter((r) => r.sitemap);
}

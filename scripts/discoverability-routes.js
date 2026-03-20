import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

export const BASE_URL = "https://digital-war-room.com";

const STATIC_PUBLIC_ROUTES = [
  { path: "/", changefreq: "daily", priority: "1.0", prerender: true, sitemap: true },
  { path: "/how-it-works", changefreq: "monthly", priority: "0.8", prerender: true, sitemap: true },
  { path: "/methodology", changefreq: "monthly", priority: "0.8", prerender: true, sitemap: true },
  { path: "/sources", changefreq: "monthly", priority: "0.8", prerender: true, sitemap: true },
  { path: "/docs/documentation", changefreq: "monthly", priority: "0.7", prerender: true, sitemap: true },
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

  return uniqueByPath([...STATIC_PUBLIC_ROUTES, ...blogRoutes]);
}

export function getPrerenderRoutes() {
  return getDiscoverabilityRoutes().filter((r) => r.prerender).map((r) => r.path);
}

export function getSitemapRoutes() {
  return getDiscoverabilityRoutes().filter((r) => r.sitemap);
}

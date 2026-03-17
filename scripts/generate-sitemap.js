/**
 * Generates sitemap.xml with lastmod for SEO.
 * Matches routes from vite.config.ts (seoPrerender). Run before build (e.g. prebuild).
 */
import { writeFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE = "https://digital-war-room.com";
const today = new Date().toISOString().slice(0, 10);

const routes = [
  { path: "/", changefreq: "daily", priority: "1.0" },
  { path: "/how-it-works", changefreq: "monthly", priority: "0.8" },
  { path: "/methodology", changefreq: "monthly", priority: "0.8" },
  { path: "/sources", changefreq: "monthly", priority: "0.8" },
  { path: "/daily-briefing", changefreq: "daily", priority: "0.9" },
  { path: "/impressum", changefreq: "yearly", priority: "0.3" },
  { path: "/privacy", changefreq: "yearly", priority: "0.3" },
  { path: "/support", changefreq: "monthly", priority: "0.5" },
  { path: "/blog", changefreq: "weekly", priority: "0.6" },
];

const urlEntries = routes
  .map(
    (r) => `  <url>
    <loc>${BASE}${r.path === "/" ? "/" : r.path}</loc>
    <lastmod>${today}</lastmod>
    <changefreq>${r.changefreq}</changefreq>
    <priority>${r.priority}</priority>
  </url>`
  )
  .join("\n");

const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urlEntries}
</urlset>
`;

const outPath = join(__dirname, "..", "public", "sitemap.xml");
writeFileSync(outPath, sitemap, "utf8");
console.log("Generated public/sitemap.xml with lastmod:", today);

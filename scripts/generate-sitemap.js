/**
 * Generates sitemap.xml with lastmod for SEO.
 * Uses the same discoverability route catalog as prerender.
 */
import { writeFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { BASE_URL, getSitemapRoutes } from "./discoverability-routes.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const today = new Date().toISOString().slice(0, 10);
const routes = getSitemapRoutes();

const urlEntries = routes
  .map(
    (r) => `  <url>
    <loc>${BASE_URL}${r.path === "/" ? "/" : r.path}</loc>
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

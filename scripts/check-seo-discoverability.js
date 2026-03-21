import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { getDiscoverabilityRoutes } from "./discoverability-routes.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const appPath = join(__dirname, "..", "src", "App.tsx");
const blogPostsPath = join(__dirname, "..", "src", "lib", "blogPosts.tsx");

const NOINDEX_ROUTES = new Set([
  "/app/dashboard",
  "/app/monitoring",
  "/newsletter/confirm",
  "/newsletter/unsubscribe",
]);

/** Redirect-only routes; canonical doc URLs live under /docs/documentation?doc=… in the sitemap. */
const LEGACY_DOC_REDIRECT_ROUTES = new Set(["/how-it-works", "/methodology", "/sources"]);

function getAppRoutes() {
  const source = readFileSync(appPath, "utf8");
  const routeRegex = /<Route\s+path="([^"]+)"/g;
  const routes = [];
  let match = routeRegex.exec(source);
  while (match) {
    if (match[1]) {
      routes.push(match[1]);
    }
    match = routeRegex.exec(source);
  }
  return routes;
}

function getBlogSlugs() {
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

function isIndexableStaticRoute(path) {
  if (path === "*" || path === "/docs") return false;
  if (path.includes(":")) return false;
  if (path.startsWith("/app/")) return false;
  if (NOINDEX_ROUTES.has(path)) return false;
  return true;
}

function main() {
  const errors = [];
  const appRoutes = getAppRoutes();
  const discoverabilityRoutes = getDiscoverabilityRoutes();
  const discoverabilityPathSet = new Set(discoverabilityRoutes.map((r) => r.path));
  const prerenderPathSet = new Set(discoverabilityRoutes.filter((r) => r.prerender).map((r) => r.path));
  const sitemapPathSet = new Set(discoverabilityRoutes.filter((r) => r.sitemap).map((r) => r.path));

  const expectedStaticIndexable = appRoutes.filter(isIndexableStaticRoute);
  for (const path of expectedStaticIndexable) {
    if (!discoverabilityPathSet.has(path)) {
      errors.push(`Missing in discoverability routes: ${path}`);
    }
    if (!prerenderPathSet.has(path)) {
      errors.push(`Missing prerender flag for route: ${path}`);
    }
    if (!LEGACY_DOC_REDIRECT_ROUTES.has(path) && !sitemapPathSet.has(path)) {
      errors.push(`Missing sitemap flag for route: ${path}`);
    }
  }

  for (const noindexPath of NOINDEX_ROUTES) {
    if (sitemapPathSet.has(noindexPath)) {
      errors.push(`Noindex route should not be in sitemap: ${noindexPath}`);
    }
  }

  const blogSlugs = getBlogSlugs();
  for (const slug of blogSlugs) {
    const route = `/blog/${slug}`;
    if (!discoverabilityPathSet.has(route)) {
      errors.push(`Blog route missing in discoverability routes: ${route}`);
    }
    if (!prerenderPathSet.has(route)) {
      errors.push(`Blog route missing prerender flag: ${route}`);
    }
    if (!sitemapPathSet.has(route)) {
      errors.push(`Blog route missing sitemap flag: ${route}`);
    }
  }

  if (!discoverabilityPathSet.has("/docs/documentation")) {
    errors.push("Missing /docs/documentation in discoverability routes");
  }

  if (errors.length > 0) {
    console.error("SEO discoverability checks failed:");
    for (const error of errors) {
      console.error(`- ${error}`);
    }
    process.exit(1);
  }

  console.log("SEO discoverability checks passed.");
}

main();

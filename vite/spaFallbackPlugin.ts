import type { Connect } from "vite";

const STATIC_EXT = /\.(?:js|mjs|css|png|jpe?g|gif|webp|svg|ico|woff2?|map|json|txt|xml)$/i;

/** Serve React SPA shell (`app/index.html`) for all non-asset routes except `/` and the static landing shell. */
function shouldRewriteToSpa(urlPath: string): boolean {
  if (urlPath === "/" || urlPath === "") return false;
  if (urlPath === "/index.html") return false;
  if (urlPath === "/app/index.html") return false;
  if (
    urlPath.startsWith("/@") ||
    urlPath.startsWith("/src") ||
    urlPath.startsWith("/node_modules") ||
    urlPath.startsWith("/__vite") ||
    urlPath.startsWith("/@fs")
  ) {
    return false;
  }
  const base = urlPath.split("?")[0] ?? urlPath;
  if (STATIC_EXT.test(base)) {
    return false;
  }
  return true;
}

function spaFallbackMiddleware(req: Connect.IncomingMessage, _res: Connect.ServerResponse, next: Connect.NextFunction) {
  const raw = req.url ?? "";
  const urlPath = raw.split("?")[0] ?? "";
  if (!shouldRewriteToSpa(urlPath)) {
    next();
    return;
  }
  const q = raw.includes("?") ? `?${raw.split("?")[1]}` : "";
  req.url = `/app/index.html${q}`;
  next();
}

export function spaFallbackPlugin() {
  return {
    name: "dwr-spa-fallback",
    configureServer(server) {
      server.middlewares.use(spaFallbackMiddleware);
    },
    configurePreviewServer(server) {
      server.middlewares.use(spaFallbackMiddleware);
    },
  };
}

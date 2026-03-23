import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { VitePWA } from "vite-plugin-pwa";
import seoPrerender from "vite-plugin-seo-prerender";
import { getPrerenderRoutes } from "./scripts/discoverability-routes.js";
import { spaFallbackPlugin } from "./vite/spaFallbackPlugin";

// https://vitejs.dev/config/
export default defineConfig(() => {
  const shouldPrerender =
    process.env.ENABLE_PRERENDER === "1" &&
    (process.env.VERCEL !== "1" || process.env.VERCEL_FORCE_PRERENDER === "1");

  return {
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "index.html"),
        app: path.resolve(__dirname, "app/index.html"),
      },
    },
  },
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
  },
  plugins: [
    react(),
    spaFallbackPlugin(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.ico", "favicon.png", "apple-touch-icon.png", "offline.html"],
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
        navigateFallback: "/app/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/$/],
        runtimeCaching: [
          {
            urlPattern: /^https?:\/\/[^/]+\/api\/.*/i,
            handler: "NetworkFirst",
            options: {
              cacheName: "api-cache",
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 },
              networkTimeoutSeconds: 10,
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
    // Vercel build images do not provide Chrome for Puppeteer by default.
    // Keep prerender opt-in there unless explicitly overridden.
    ...(shouldPrerender
      ? [
          seoPrerender({
            routes: getPrerenderRoutes(),
            puppeteer:
              process.env.CI === "true"
                ? { args: ["--no-sandbox", "--disable-setuid-sandbox"] }
                : undefined,
          }),
        ]
      : []),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  };
});

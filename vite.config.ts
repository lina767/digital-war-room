import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { VitePWA } from "vite-plugin-pwa";
import seoPrerender from "vite-plugin-seo-prerender";
import { getPrerenderRoutes } from "./scripts/discoverability-routes.js";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
  },
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
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
    // Prerender public routes to emit route-specific HTML metadata for crawlers and social scrapers.
    ...(process.env.ENABLE_PRERENDER === "1"
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
}));

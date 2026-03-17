import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import seoPrerender from "vite-plugin-seo-prerender";

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
    // Prerender uses Puppeteer/Chrome; not available on Vercel/CI. Only run when explicitly enabled (e.g. local ENABLE_PRERENDER=1).
    ...(process.env.ENABLE_PRERENDER === "1"
      ? [
          seoPrerender({
            routes: [
              "/",
              "/how-it-works",
              "/methodology",
              "/sources",
              "/daily-briefing",
              "/impressum",
              "/privacy",
              "/support",
            ],
            // Required in CI (e.g. GitHub Actions) where Chrome runs in a sandboxed environment.
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

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
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));

import { registerSW } from "virtual:pwa-register";

/**
 * Registers the service worker in production.
 * On a new deployment, force-activate the new SW and reload once so stale UI cache is cleared.
 */
export function registerPwaServiceWorker(): void {
  if (!import.meta.env.PROD) return;

  try {
    const updateSW = registerSW({
      immediate: true,
      onNeedRefresh() {
        // Force immediate activation of the updated worker and one client reload.
        void updateSW(true);
        if (typeof window !== "undefined") {
          import("sonner").then(({ toast }) => {
            toast.message("Update installed", {
              description: "Reloading to apply the latest frontend build.",
              duration: 2_500,
            });
          });
          window.setTimeout(() => window.location.reload(), 300);
        }
      },
      onOfflineReady() {
        if (typeof window !== "undefined" && window.innerWidth > 1023) return;
        import("sonner").then(({ toast }) => {
          toast.message("Offline ready", {
            description: "Cached pages open without a network connection.",
            duration: 5_000,
          });
        });
      },
    });
  } catch {
    // virtual module missing in dev without PWA plugin
  }
}

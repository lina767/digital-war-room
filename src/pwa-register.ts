import { registerSW } from "virtual:pwa-register";

/**
 * Registers the service worker in production; shows a short toast when offline cache is ready.
 */
export function registerPwaServiceWorker(): void {
  if (!import.meta.env.PROD) return;

  try {
    registerSW({
      immediate: true,
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

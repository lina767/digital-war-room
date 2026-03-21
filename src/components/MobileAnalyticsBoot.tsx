import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { isMobileViewport, isPwaStandalone, trackMobilePageView } from "@/lib/mobileAnalytics";

/**
 * Route-aware mobile + PWA context for analytics (does not alter desktop behavior).
 */
export function MobileAnalyticsBoot() {
  const location = useLocation();

  useEffect(() => {
    trackMobilePageView(location.pathname);
  }, [location.pathname]);

  useEffect(() => {
    if (!isMobileViewport() || !isPwaStandalone()) return;
    try {
      document.documentElement.dataset.pwaStandalone = "true";
    } catch {
      // ignore
    }
  }, []);

  return null;
}

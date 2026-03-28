import { lazy, Suspense, useEffect, useState } from "react";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PageSkeleton } from "@/components/ui/skeleton";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Analytics } from "@vercel/analytics/react";
import { MobileAnalyticsBoot } from "@/components/MobileAnalyticsBoot";
import { getAnalyticsConsent, type AnalyticsConsent } from "@/lib/analyticsConsent";

const DOCS_HUB = "/docs/documentation";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const AgentMonitor = lazy(() => import("./pages/AgentMonitor"));
const NotFound = lazy(() => import("./pages/NotFound"));
const Impressum = lazy(() => import("./pages/Impressum"));
const DailyBriefingPage = lazy(() => import("./pages/DailyBriefingPage"));
const Documentation = lazy(() => import("./pages/Documentation"));
const Newsletter = lazy(() => import("./pages/Newsletter"));
const NewsletterConfirm = lazy(() => import("./pages/NewsletterConfirm"));
const NewsletterUnsubscribe = lazy(() => import("./pages/NewsletterUnsubscribe"));
const Privacy = lazy(() => import("./pages/Privacy"));
const Support = lazy(() => import("./pages/Support"));
const Blog = lazy(() => import("./pages/Blog"));
const BlogPost = lazy(() => import("./pages/BlogPost"));
const DemoPage = lazy(() => import("./pages/DemoPage"));
const Login = lazy(() => import("./pages/Login"));
const InvestigationWorkspacePage = lazy(() => import("./pages/InvestigationWorkspacePage"));

function PageFallback() {
  return <PageSkeleton />;
}

const App = () => {
  const [analyticsConsent, setAnalyticsConsent] = useState<AnalyticsConsent | null>(() => getAnalyticsConsent());

  useEffect(() => {
    void import("./pwa-register").then((m) => m.registerPwaServiceWorker());
  }, []);

  useEffect(() => {
    const onConsentChange = () => setAnalyticsConsent(getAnalyticsConsent());
    window.addEventListener("dwr-analytics-consent-changed", onConsentChange);
    return () => window.removeEventListener("dwr-analytics-consent-changed", onConsentChange);
  }, []);

  return (
  <TooltipProvider>
    <Sonner />
    <BrowserRouter>
      {analyticsConsent === "granted" ? <MobileAnalyticsBoot /> : null}
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/demo" element={<DemoPage />} />
          <Route path="/app/login" element={<Login />} />
          <Route path="/app/dashboard" element={<Dashboard />} />
          <Route path="/app/monitoring" element={<AgentMonitor />} />
          <Route path="/app/investigation" element={<InvestigationWorkspacePage />} />
          <Route path="/how-it-works" element={<Navigate to={`${DOCS_HUB}?doc=how-it-works`} replace />} />
          <Route path="/methodology" element={<Navigate to={`${DOCS_HUB}?doc=methodology`} replace />} />
          <Route path="/sources" element={<Navigate to={`${DOCS_HUB}?doc=source-directory`} replace />} />
          <Route path="/daily-briefing" element={<DailyBriefingPage />} />
          <Route path="/docs/documentation" element={<Documentation />} />
          <Route path="/docs" element={<Navigate to="/docs/documentation" replace />} />
          <Route path="/newsletter" element={<Newsletter />} />
          <Route path="/newsletter/confirm" element={<NewsletterConfirm />} />
          <Route path="/newsletter/unsubscribe" element={<NewsletterUnsubscribe />} />
          <Route path="/impressum" element={<Impressum />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/support" element={<Support />} />
          <Route path="/blog" element={<Blog />} />
          <Route path="/blog/:slug" element={<BlogPost />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
    {analyticsConsent === "granted" ? <Analytics /> : null}
  </TooltipProvider>
  );
};

export default App;

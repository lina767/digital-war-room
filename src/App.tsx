import { lazy, Suspense, useEffect } from "react";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PageSkeleton } from "@/components/ui/skeleton";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Analytics } from "@vercel/analytics/react";
import { MobileAnalyticsBoot } from "@/components/MobileAnalyticsBoot";

const DOCS_HUB = "/docs/documentation";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const AgentMonitor = lazy(() => import("./pages/AgentMonitor"));
const NotFound = lazy(() => import("./pages/NotFound"));
const Impressum = lazy(() => import("./pages/Impressum"));
const DailyIntelligenceBriefing = lazy(() => import("./pages/DailyIntelligenceBriefing"));
const Documentation = lazy(() => import("./pages/Documentation"));
const Newsletter = lazy(() => import("./pages/Newsletter"));
const NewsletterConfirm = lazy(() => import("./pages/NewsletterConfirm"));
const NewsletterUnsubscribe = lazy(() => import("./pages/NewsletterUnsubscribe"));
const Privacy = lazy(() => import("./pages/Privacy"));
const Support = lazy(() => import("./pages/Support"));
const Blog = lazy(() => import("./pages/Blog"));
const BlogPost = lazy(() => import("./pages/BlogPost"));

function PageFallback() {
  return <PageSkeleton />;
}

const App = () => {
  useEffect(() => {
    void import("./pwa-register").then((m) => m.registerPwaServiceWorker());
  }, []);

  return (
  <TooltipProvider>
    <Sonner />
    <BrowserRouter>
      <MobileAnalyticsBoot />
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/app/dashboard" element={<Dashboard />} />
          <Route path="/app/monitoring" element={<AgentMonitor />} />
          <Route path="/how-it-works" element={<Navigate to={`${DOCS_HUB}?doc=how-it-works`} replace />} />
          <Route path="/methodology" element={<Navigate to={`${DOCS_HUB}?doc=methodology`} replace />} />
          <Route path="/sources" element={<Navigate to={`${DOCS_HUB}?doc=source-directory`} replace />} />
          <Route path="/daily-briefing" element={<DailyIntelligenceBriefing />} />
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
    <Analytics />
  </TooltipProvider>
  );
};

export default App;

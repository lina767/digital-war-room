import { lazy, Suspense } from "react";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PageSkeleton } from "@/components/ui/skeleton";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Analytics } from "@vercel/analytics/react";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const AgentMonitor = lazy(() => import("./pages/AgentMonitor"));
const NotFound = lazy(() => import("./pages/NotFound"));
const HowItWorks = lazy(() => import("./pages/HowItWorks"));
const Methodology = lazy(() => import("./pages/Methodology"));
const Impressum = lazy(() => import("./pages/Impressum"));
const SourceDirectory = lazy(() => import("./pages/SourceDirectory"));
const DailyIntelligenceBriefing = lazy(() => import("./pages/DailyIntelligenceBriefing"));
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

const App = () => (
  <TooltipProvider>
    <Sonner />
    <BrowserRouter>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/app/dashboard" element={<Dashboard />} />
          <Route path="/app/monitoring" element={<AgentMonitor />} />
          <Route path="/how-it-works" element={<HowItWorks />} />
          <Route path="/methodology" element={<Methodology />} />
          <Route path="/sources" element={<SourceDirectory />} />
          <Route path="/daily-briefing" element={<DailyIntelligenceBriefing />} />
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

export default App;

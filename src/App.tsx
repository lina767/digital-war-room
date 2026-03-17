import { lazy, Suspense } from "react";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
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
const Privacy = lazy(() => import("./pages/Privacy"));
const Support = lazy(() => import("./pages/Support"));

function PageFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background" aria-busy="true" aria-label="Loading">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
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
          <Route path="/impressum" element={<Impressum />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/support" element={<Support />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
    <Analytics />
  </TooltipProvider>
);

export default App;

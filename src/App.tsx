import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { Analytics } from "@vercel/analytics/react";
import Dashboard from "./pages/Dashboard";
import NotFound from "./pages/NotFound";
import { RootRedirect } from "./components/RootRedirect";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<RootRedirect />} />
            <Route path="/app/dashboard" element={<Dashboard />} />
            {/* Alte Login/Signup-URLs direkt auf Dashboard umleiten */}
            <Route path="/login" element={<Navigate to="/app/dashboard" replace />} />
            <Route path="/signup" element={<Navigate to="/app/dashboard" replace />} />
            <Route path="/reset-password" element={<Navigate to="/app/dashboard" replace />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
      <Analytics />
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;

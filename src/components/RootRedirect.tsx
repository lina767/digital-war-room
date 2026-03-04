import { useAuth } from "@/contexts/AuthContext";
import { Navigate } from "react-router-dom";

/**
 * Root path "/": redirect to dashboard when logged in, otherwise to login.
 * Ensures the app is fully behind login for production.
 */
export function RootRedirect() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="font-mono text-primary text-glow animate-pulse">INITIALIZING...</div>
      </div>
    );
  }

  if (user) {
    return <Navigate to="/app/dashboard" replace />;
  }

  return <Navigate to="/login" replace />;
}

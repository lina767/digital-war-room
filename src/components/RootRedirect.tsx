import { Navigate } from "react-router-dom";

/**
 * Root path "/": redirect to dashboard. App is used without login.
 */
export function RootRedirect() {
  return <Navigate to="/app/dashboard" replace />;
}

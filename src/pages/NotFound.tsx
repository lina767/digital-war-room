import { useLocation, Link } from "react-router-dom";
import { useEffect } from "react";
import { ArrowLeft } from "lucide-react";
import { SEO } from "@/components/SEO";
import { TITLE_404 } from "@/lib/seoCopy";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <>
      <SEO title={TITLE_404} path={location.pathname} noindex />
      <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="text-center space-y-4">
        <p className="font-mono text-xs tracking-[0.28em] text-muted-foreground uppercase">
          SIGNAL NOT FOUND
        </p>
        <h1 className="text-5xl font-bold font-mono text-primary text-glow">404</h1>
        <p className="text-sm text-muted-foreground max-w-xs mx-auto">
          The requested route <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">{location.pathname}</code> does not exist.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-sm text-primary hover:text-primary/90 transition-colors touch-manipulation"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Return to Dashboard
        </Link>
      </div>
    </div>
    </>
  );
};

export default NotFound;

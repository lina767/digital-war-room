import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";

interface ContentPageLayoutProps {
  label: string;
  title: string;
  description?: string;
  icon?: React.ReactNode;
  maxWidth?: "sm" | "md" | "lg" | "xl" | "2xl" | "3xl" | "4xl" | "5xl";
  children: React.ReactNode;
  /** Hide back-to-dashboard link when printing (e.g. documentation PDF export). */
  printHideNavigation?: boolean;
}

const MAX_W_MAP: Record<string, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
  "2xl": "max-w-2xl",
  "3xl": "max-w-3xl",
  "4xl": "max-w-4xl",
  "5xl": "max-w-5xl",
};

export function ContentPageLayout({
  label,
  title,
  description,
  icon,
  maxWidth = "4xl",
  children,
  printHideNavigation = false,
}: ContentPageLayoutProps) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className={cn("mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-10", MAX_W_MAP[maxWidth])}>
        <div
          className={cn(
            "mb-6 sm:mb-8 flex items-center justify-between gap-3",
            printHideNavigation && "print:hidden",
          )}
        >
          <Link
            to="/app/dashboard"
            className="inline-flex items-center gap-2 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors touch-manipulation"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            <span>Back to dashboard</span>
          </Link>
        </div>

        <header className="mb-8 sm:mb-10">
          <div className="flex items-center gap-3 mb-3">
            {icon && (
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border" aria-hidden>
                {icon}
              </span>
            )}
            <p className="font-mono text-[11px] sm:text-xs tracking-[0.28em] text-muted-foreground uppercase">
              {label}
            </p>
          </div>
          <h1 className="text-2xl sm:text-3xl md:text-4xl font-semibold tracking-tight mb-3">
            {title}
          </h1>
          {description && (
            <p className="text-sm sm:text-base text-muted-foreground max-w-3xl">
              {description}
            </p>
          )}
        </header>

        <main>{children}</main>
      </div>
    </div>
  );
}

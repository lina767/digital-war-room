import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface DocsLayoutProps {
  sidebar: ReactNode;
  article: ReactNode;
  toc: ReactNode;
}

export function DocsLayout({ sidebar, article, toc }: DocsLayoutProps) {
  return (
    <div className="grid grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_240px] gap-6 xl:gap-8">
      <aside className={cn("xl:sticky xl:top-6 xl:self-start h-fit print:hidden")} aria-label="Documentation topics">
        {sidebar}
      </aside>
      <section className="min-w-0">{article}</section>
      <aside className={cn("hidden xl:block xl:sticky xl:top-6 xl:self-start h-fit print:hidden")}>{toc}</aside>
    </div>
  );
}

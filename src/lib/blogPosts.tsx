import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { DOCS_HOW_IT_WORKS, DOCS_METHODOLOGY, DOCS_SOURCE_DIRECTORY } from "@/lib/docLinks";

/**
 * Blog posts for the Digital War Room. Add entries here or later replace with CMS/API.
 */

export type BlogSeries = "weekly-insights";

export const BLOG_SERIES_LABELS: Record<BlogSeries, string> = {
  "weekly-insights": "Weekly insights",
};

export interface BlogPost {
  slug: string;
  title: string;
  date: string; // ISO date (YYYY-MM-DD)
  excerpt: string;
  body: ReactNode;
  /** Shown as a small label on listing and post (e.g. Weekly insights). */
  series?: BlogSeries;
}

export const BLOG_POSTS: BlogPost[] = [
  {
    slug: "weekly-insights-auto-generated-summaries",
    series: "weekly-insights",
    title: "Weekly insights: auto-generated analysis summaries",
    date: "2026-03-21",
    excerpt:
      "What “weekly insights” means here: synthesized readouts from the multi-agent analysis pipeline, not editorial opinion.",
    body: (
      <>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          <strong className="text-foreground font-medium">Weekly insights</strong> are short,
          auto-generated summaries derived from the same analysis stack that powers the
          dashboard: FININT, SIGINT, GEOINT, news, cyber, energy, and related streams fused
          by the supervisor into escalation scores, key findings, scenarios, and compliance
          context. They reflect what the pipeline measured in a given window — not a separate
          editorial column.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          On the live app, the closest surface is the{" "}
          <span className="text-foreground/90">Updated Briefing</span> and related panels after
          each run: recap, key findings, predictive outlook, and sanctions/compliance blocks are
          all synthesized from agent outputs. When we publish weekly insight notes on this blog,
          they condense or highlight patterns from that process for readers who want the gist
          without opening the full dashboard.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          For a daily email version of the briefing for a chosen conflict, see the{" "}
          <Link to="/newsletter" className="text-primary hover:underline">
            Daily Briefing newsletter
          </Link>
          . The blog’s weekly line is complementary: longer-horizon or thematic summaries
          rather than every daily delta.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
          Technical background:{" "}
          <Link to={DOCS_HOW_IT_WORKS} className="text-primary hover:underline">
            How it works
          </Link>
          ,{" "}
          <Link to={DOCS_METHODOLOGY} className="text-primary hover:underline">
            Methodology
          </Link>
          , and{" "}
          <Link to={DOCS_SOURCE_DIRECTORY} className="text-primary hover:underline">
            Source Directory
          </Link>
          .
        </p>
      </>
    ),
  },
  {
    slug: "welcome-to-the-blog",
    title: "Welcome to the Digital War Room Blog",
    date: "2025-03-17",
    excerpt:
      "Updates, methodology notes, weekly insights, and context on how we build and run the platform.",
    body: (
      <>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          This blog hosts short updates on the platform: new data sources, methodology
          changes,{" "}
          <Link
            to="/blog/weekly-insights-auto-generated-summaries"
            className="text-primary hover:underline"
          >
            weekly insights
          </Link>{" "}
          (auto-generated analysis summaries), and occasional notes on conflict monitoring and
          OSINT. No fluff — just what matters for understanding how the Digital War Room works
          and what it can do.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
          For a full overview of the system, see{" "}
          <Link to={DOCS_HOW_IT_WORKS} className="text-primary hover:underline">How it works</Link>
          {" "}and the{" "}
          <Link to={DOCS_METHODOLOGY} className="text-primary hover:underline">Methodology</Link>
          {" "}page, and the{" "}
          <Link to={DOCS_SOURCE_DIRECTORY} className="text-primary hover:underline">Source Directory</Link>
          {" "}for sources and reliability ratings.
        </p>
      </>
    ),
  },
];

/** Get post by slug, or undefined if not found. */
export function getPostBySlug(slug: string): BlogPost | undefined {
  return BLOG_POSTS.find((p) => p.slug === slug);
}

/** All slugs for static routes / sitemap. */
export function getAllSlugs(): string[] {
  return BLOG_POSTS.map((p) => p.slug);
}

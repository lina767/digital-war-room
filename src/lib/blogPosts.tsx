import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/**
 * Blog posts for the Digital War Room. Add entries here or later replace with CMS/API.
 */

export interface BlogPost {
  slug: string;
  title: string;
  date: string; // ISO date (YYYY-MM-DD)
  excerpt: string;
  body: ReactNode;
}

export const BLOG_POSTS: BlogPost[] = [
  {
    slug: "welcome-to-the-blog",
    title: "Welcome to the Digital War Room Blog",
    date: "2025-03-17",
    excerpt:
      "Updates, methodology notes, and context on how we build and run the platform.",
    body: (
      <>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl mb-4">
          This blog will host short updates on the platform: new data sources, methodology
          changes, and occasional notes on conflict monitoring and OSINT. No fluff — just
          what matters for understanding how the Digital War Room works and what it can do.
        </p>
        <p className="text-sm sm:text-[15px] text-muted-foreground max-w-3xl">
          For a full overview of the system, see{" "}
          <Link to="/how-it-works" className="text-primary hover:underline">How it works</Link>
          {" "}and the{" "}
          <Link to="/methodology" className="text-primary hover:underline">Methodology</Link>
          {" "}page, and the{" "}
          <Link to="/sources" className="text-primary hover:underline">Source Directory</Link>
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

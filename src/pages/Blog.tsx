import { Link } from "react-router-dom";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";
import { BLOG_POSTS, BLOG_SERIES_LABELS } from "@/lib/blogPosts";
import { TITLE_BLOG, DESCRIPTION_BLOG } from "@/lib/seoCopy";
import { Calendar, ArrowRight } from "lucide-react";

const blogStructuredData = {
  "@type": "Blog",
  "@id": "https://digital-war-room.com/blog#blog",
  url: "https://digital-war-room.com/blog",
  name: "Digital War Room Blog",
  description: DESCRIPTION_BLOG,
  inLanguage: "en",
  blogPost: BLOG_POSTS.map((post) => ({
    "@type": "BlogPosting",
    "@id": `https://digital-war-room.com/blog/${post.slug}#blogposting`,
    url: `https://digital-war-room.com/blog/${post.slug}`,
    headline: post.title,
    datePublished: post.date,
    dateModified: post.date,
    description: post.excerpt,
  })),
};

const Blog = () => {
  return (
    <>
      <SEO
        title={TITLE_BLOG}
        description={DESCRIPTION_BLOG}
        path="/blog"
        pageType="Blog"
        structuredData={blogStructuredData}
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Blog", url: "https://digital-war-room.com/blog" },
        ]}
      />
      <ContentPageLayout
        label="BLOG"
        title="Blog"
        description={DESCRIPTION_BLOG}
        maxWidth="3xl"
      >
        <ul className="space-y-6 sm:space-y-8">
          {BLOG_POSTS.map((post) => (
            <li key={post.slug}>
              <Link
                to={`/blog/${post.slug}`}
                className="group block rounded-lg border border-border bg-card/40 p-4 sm:p-5 hover:border-primary/40 hover:bg-card/60 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50"
              >
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] sm:text-xs text-muted-foreground font-mono tracking-wide mb-2">
                  {post.series ? (
                    <span className="inline-flex rounded border border-primary/35 bg-primary/10 px-2 py-0.5 text-[10px] font-sans font-medium tracking-normal text-primary">
                      {BLOG_SERIES_LABELS[post.series]}
                    </span>
                  ) : null}
                  <span className="inline-flex items-center gap-2">
                    <Calendar className="h-3.5 w-3.5" aria-hidden />
                    <time dateTime={post.date}>
                      {new Date(post.date + "T12:00:00").toLocaleDateString("en-GB", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </time>
                  </span>
                </div>
                <h2 className="text-lg sm:text-xl font-semibold tracking-tight mb-2 group-hover:text-primary transition-colors">
                  {post.title}
                </h2>
                <p className="text-sm text-muted-foreground max-w-2xl mb-3">
                  {post.excerpt}
                </p>
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-primary group-hover:underline">
                  Read post
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
                </span>
              </Link>
            </li>
          ))}
        </ul>
        {BLOG_POSTS.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No posts yet. Check back later.
          </p>
        )}
      </ContentPageLayout>
    </>
  );
};

export default Blog;

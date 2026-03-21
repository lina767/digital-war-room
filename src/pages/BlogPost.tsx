import { useParams, Link } from "react-router-dom";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";
import { getPostBySlug, BLOG_SERIES_LABELS } from "@/lib/blogPosts";
import { Calendar, ArrowLeft } from "lucide-react";
import NotFound from "@/pages/NotFound";

const BlogPost = () => {
  const { slug } = useParams<{ slug: string }>();
  const post = slug ? getPostBySlug(slug) : undefined;

  if (!post) {
    return <NotFound />;
  }

  const formattedDate = new Date(post.date + "T12:00:00").toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const blogPostStructuredData = {
    "@type": "BlogPosting",
    "@id": `https://digital-war-room.com/blog/${post.slug}#blogposting`,
    url: `https://digital-war-room.com/blog/${post.slug}`,
    mainEntityOfPage: `https://digital-war-room.com/blog/${post.slug}`,
    headline: post.title,
    description: post.excerpt,
    datePublished: post.date,
    dateModified: post.date,
    inLanguage: "en",
    image: "https://digital-war-room.com/og-image.png",
    author: {
      "@type": "Organization",
      "@id": "https://digital-war-room.com/#organization",
      name: "Digital War Room",
    },
    publisher: {
      "@type": "Organization",
      "@id": "https://digital-war-room.com/#organization",
      name: "Digital War Room",
      logo: {
        "@type": "ImageObject",
        url: "https://digital-war-room.com/favicon.png",
      },
    },
  };

  return (
    <>
      <SEO
        title={`${post.title} — Digital War Room Blog`}
        description={post.excerpt}
        path={`/blog/${post.slug}`}
        pageType="BlogPosting"
        datePublished={post.date}
        dateModified={post.date}
        structuredData={blogPostStructuredData}
        breadcrumbs={[
          { name: "Home", url: "https://digital-war-room.com/" },
          { name: "Blog", url: "https://digital-war-room.com/blog" },
          { name: post.title, url: `https://digital-war-room.com/blog/${post.slug}` },
        ]}
      />
      <ContentPageLayout
        label="BLOG"
        title={post.title}
        description={post.excerpt}
        maxWidth="3xl"
      >
        <div className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] sm:text-xs text-muted-foreground font-mono tracking-wide">
          {post.series ? (
            <span className="inline-flex rounded border border-primary/35 bg-primary/10 px-2 py-0.5 text-[10px] font-sans font-medium tracking-normal text-primary">
              {BLOG_SERIES_LABELS[post.series]}
            </span>
          ) : null}
          <span className="inline-flex items-center gap-2">
            <Calendar className="h-3.5 w-3.5" aria-hidden />
            <time dateTime={post.date}>{formattedDate}</time>
          </span>
        </div>
        <article className="space-y-4 text-foreground">
          {post.body}
        </article>
        <div className="mt-8 pt-6 border-t border-border">
          <Link
            to="/blog"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/50 rounded"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Back to blog
          </Link>
        </div>
      </ContentPageLayout>
    </>
  );
};

export default BlogPost;

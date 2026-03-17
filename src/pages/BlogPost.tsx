import { useParams, Link } from "react-router-dom";
import { ContentPageLayout } from "@/components/ContentPageLayout";
import { SEO } from "@/components/SEO";
import { getPostBySlug } from "@/lib/blogPosts";
import { Calendar, ArrowLeft } from "lucide-react";
import { NotFound } from "@/pages/NotFound";

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

  return (
    <>
      <SEO
        title={`${post.title} — Digital War Room Blog`}
        description={post.excerpt}
        path={`/blog/${post.slug}`}
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
        <div className="mb-6 flex items-center gap-2 text-[11px] sm:text-xs text-muted-foreground font-mono tracking-wide">
          <Calendar className="h-3.5 w-3.5" aria-hidden />
          <time dateTime={post.date}>{formattedDate}</time>
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

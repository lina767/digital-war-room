import { useMemo, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface DocsArticleProps {
  markdown: string;
}

interface TocItem {
  level: 2 | 3;
  text: string;
  slug: string;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

function extractToc(markdown: string): TocItem[] {
  const lines = markdown.split("\n");
  const out: TocItem[] = [];
  const used = new Map<string, number>();

  for (const line of lines) {
    const h2 = line.match(/^##\s+(.+)$/);
    const h3 = line.match(/^###\s+(.+)$/);
    const target = h2 ?? h3;
    if (!target) continue;

    const level: 2 | 3 = h2 ? 2 : 3;
    const text = target[1].trim();
    const baseSlug = slugify(text);
    const count = used.get(baseSlug) ?? 0;
    used.set(baseSlug, count + 1);
    const slug = count === 0 ? baseSlug : `${baseSlug}-${count}`;
    out.push({ level, text, slug });
  }

  return out;
}

function extractText(children: ReactNode): string {
  if (typeof children === "string") return children;
  if (typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(extractText).join("");
  if (children && typeof children === "object" && "props" in children) {
    return extractText((children as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

function buildHeadingRenderer(tag: "h2" | "h3", seen: Map<string, number>): Components["h2"] {
  const className =
    tag === "h2" ? "text-2xl sm:text-3xl font-semibold tracking-tight mt-10 mb-4" : "text-xl sm:text-2xl font-semibold tracking-tight mt-8 mb-3";
  return function Heading({ children }) {
    const text = extractText(children);
    const baseSlug = slugify(text);
    const count = seen.get(baseSlug) ?? 0;
    seen.set(baseSlug, count + 1);
    const slug = count === 0 ? baseSlug : `${baseSlug}-${count}`;
    const Tag = tag;
    return (
      <Tag id={slug} className={className}>
        {children}
      </Tag>
    );
  };
}

export function DocsArticle({ markdown }: DocsArticleProps) {
  const markdownComponents = useMemo<Components>(() => {
    const seen = new Map<string, number>();
    return {
      h2: buildHeadingRenderer("h2", seen),
      h3: buildHeadingRenderer("h3", seen),
      h1: ({ children }) => <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mb-5">{children}</h1>,
      p: ({ children }) => <p className="text-sm sm:text-base text-muted-foreground leading-7 my-3">{children}</p>,
      ul: ({ children }) => <ul className="list-disc pl-6 space-y-1.5 my-3 text-sm sm:text-base text-muted-foreground">{children}</ul>,
      ol: ({ children }) => <ol className="list-decimal pl-6 space-y-1.5 my-3 text-sm sm:text-base text-muted-foreground">{children}</ol>,
      li: ({ children }) => <li>{children}</li>,
      hr: () => <hr className="my-8 border-border" />,
      blockquote: ({ children }) => (
        <blockquote className="border-l-2 border-border pl-4 italic text-muted-foreground my-5">{children}</blockquote>
      ),
      code: ({ inline, children, ...props }) =>
        inline ? (
          <code className="rounded bg-muted px-1 py-0.5 text-[0.85em]" {...props}>
            {children}
          </code>
        ) : (
          <code className="block overflow-x-auto rounded-lg border border-border bg-card/60 p-3 text-xs sm:text-sm" {...props}>
            {children}
          </code>
        ),
      a: ({ href, children }) => (
        <a
          href={href}
          target={href?.startsWith("http") ? "_blank" : undefined}
          rel={href?.startsWith("http") ? "noopener noreferrer" : undefined}
          className="text-primary hover:underline"
        >
          {children}
        </a>
      ),
      table: ({ children }) => (
        <div className="overflow-x-auto my-5">
          <table className="w-full border-collapse text-sm">{children}</table>
        </div>
      ),
      th: ({ children }) => <th className="border border-border bg-muted/40 px-3 py-2 text-left font-medium">{children}</th>,
      td: ({ children }) => <td className="border border-border px-3 py-2 align-top text-muted-foreground">{children}</td>,
    };
  }, []);

  return (
    <article className="rounded-xl border border-border bg-card/25 p-5 sm:p-8">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {markdown}
      </ReactMarkdown>
    </article>
  );
}

export function DocsToc({ markdown }: { markdown: string }) {
  const toc = useMemo(() => extractToc(markdown), [markdown]);
  return (
    <div className="rounded-xl border border-border bg-card/25 p-4">
      <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground mb-3">On this page</h2>
      {toc.length === 0 ? (
        <p className="text-xs text-muted-foreground">No headings available.</p>
      ) : (
        <ul className="space-y-1.5">
          {toc.map((item) => (
            <li key={`${item.slug}-${item.level}`} className={item.level === 3 ? "ml-3" : ""}>
              <a href={`#${item.slug}`} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                {item.text}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

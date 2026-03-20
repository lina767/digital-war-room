import { Helmet } from "react-helmet-async";

const SITE_URL = "https://digital-war-room.com";
const DEFAULT_OG_IMAGE = `${SITE_URL}/og-image.png`;
const WEBSITE_ID = `${SITE_URL}/#website`;
const SOFTWARE_ID = `${SITE_URL}/#software`;

type JsonLdNode = Record<string, unknown>;
type PageType = "WebPage" | "CollectionPage" | "Blog" | "BlogPosting" | "FAQPage";

export interface SEOProps {
  title: string;
  description?: string;
  path?: string;
  image?: string;
  imageAlt?: string;
  lang?: string;
  noindex?: boolean;
  /** JSON-LD structured data objects (e.g. FAQPage, BreadcrumbList) */
  structuredData?: object | object[];
  /** Breadcrumb items for BreadcrumbList schema: [{ name, url }, ...] */
  breadcrumbs?: { name: string; url: string }[];
  /** Schema.org page type for default page-level JSON-LD node */
  pageType?: PageType;
  /** Optional published date for article-like pages (ISO date) */
  datePublished?: string;
  /** Optional modified date for article-like pages (ISO date) */
  dateModified?: string;
}

export function SEO({
  title,
  description,
  path = "",
  image = DEFAULT_OG_IMAGE,
  imageAlt,
  lang,
  noindex,
  structuredData,
  breadcrumbs,
  pageType = "WebPage",
  datePublished,
  dateModified,
}: SEOProps) {
  const canonical = path ? `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}` : SITE_URL;
  const imageUrl = image.startsWith("http") ? image : `${SITE_URL}${image.startsWith("/") ? image : `/${image}`}`;
  const ogType = pageType === "BlogPosting" ? "article" : "website";
  const pageId = `${canonical}#page`;
  const breadcrumbId = `${canonical}#breadcrumb`;

  const pageNode: JsonLdNode = {
    "@type": pageType,
    "@id": pageId,
    url: canonical,
    name: title,
    isPartOf: { "@id": WEBSITE_ID },
    about: { "@id": SOFTWARE_ID },
    primaryImageOfPage: imageUrl,
  };
  if (description) {
    pageNode.description = description;
  }
  if (datePublished) {
    pageNode.datePublished = datePublished;
  }
  if (dateModified) {
    pageNode.dateModified = dateModified;
  }
  if (pageType === "BlogPosting") {
    pageNode.mainEntityOfPage = { "@id": canonical };
    pageNode.headline = title;
    pageNode.publisher = { "@id": `${SITE_URL}/#organization` };
  }

  const graphNodes: JsonLdNode[] = [pageNode];
  if (breadcrumbs?.length) {
    graphNodes.push({
      "@type": "BreadcrumbList",
      "@id": breadcrumbId,
      itemListElement: breadcrumbs.map((item, i) => ({
        "@type": "ListItem",
        position: i + 1,
        name: item.name,
        item: item.url.startsWith("http") ? item.url : `${SITE_URL}${item.url.startsWith("/") ? item.url : `/${item.url}`}`,
      })),
    });
  }

  const normalizeStructuredData = (data: object | object[]): JsonLdNode[] => {
    const list = Array.isArray(data) ? data : [data];
    return list.flatMap((item) => {
      const node = item as JsonLdNode;
      if (Array.isArray(node["@graph"])) {
        return (node["@graph"] as JsonLdNode[]).map(({ "@context": _ignored, ...graphNode }) => graphNode);
      }
      const { "@context": _ignored, ...rest } = node;
      return [rest];
    });
  };

  if (structuredData) {
    graphNodes.push(...normalizeStructuredData(structuredData));
  }

  const jsonLdPayload = {
    "@context": "https://schema.org",
    "@graph": graphNodes,
  };

  return (
    <Helmet>
      <title>{title}</title>
      {description && <meta name="description" content={description} />}
      <link rel="canonical" href={canonical} />
      {noindex && <meta name="robots" content="noindex, nofollow" />}

      <meta property="og:title" content={title} />
      {description && <meta property="og:description" content={description} />}
      <meta property="og:url" content={canonical} />
      <meta property="og:image" content={imageUrl} />
      <meta property="og:type" content={ogType} />
      <meta property="og:site_name" content="Digital War Room" />
      <meta property="og:locale" content={lang === "de" ? "de_DE" : "en_US"} />
      <meta property="og:locale:alternate" content={lang === "de" ? "en_US" : "de_DE"} />

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:site" content="@digitalwarroom" />
      <meta name="twitter:title" content={title} />
      {description && <meta name="twitter:description" content={description} />}
      <meta name="twitter:image" content={imageUrl} />
      {imageAlt && <meta name="twitter:image:alt" content={imageAlt} />}

      {lang && <html lang={lang} />}
      <script type="application/ld+json">{JSON.stringify(jsonLdPayload)}</script>
    </Helmet>
  );
}

import { Helmet } from "react-helmet-async";

const SITE_URL = "https://digital-war-room.com";
const DEFAULT_OG_IMAGE = `${SITE_URL}/og-image.png`;

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
}: SEOProps) {
  const canonical = path ? `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}` : SITE_URL;
  const imageUrl = image.startsWith("http") ? image : `${SITE_URL}${image.startsWith("/") ? image : `/${image}`}`;

  const jsonLd: object[] = [];
  if (breadcrumbs?.length) {
    jsonLd.push({
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: breadcrumbs.map((item, i) => ({
        "@type": "ListItem",
        position: i + 1,
        name: item.name,
        item: item.url.startsWith("http") ? item.url : `${SITE_URL}${item.url.startsWith("/") ? item.url : `/${item.url}`}`,
      })),
    });
  }
  if (structuredData) {
    if (Array.isArray(structuredData)) {
      jsonLd.push(...structuredData);
    } else {
      jsonLd.push(structuredData);
    }
  }

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
      <meta property="og:type" content="website" />
      <meta property="og:locale" content={lang === "de" ? "de_DE" : "en_US"} />
      <meta property="og:locale:alternate" content={lang === "de" ? "en_US" : "de_DE"} />

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={title} />
      {description && <meta name="twitter:description" content={description} />}
      <meta name="twitter:image" content={imageUrl} />
      {imageAlt && <meta name="twitter:image:alt" content={imageAlt} />}

      {lang && <html lang={lang} />}
      {jsonLd.length > 0 && (
        <script type="application/ld+json">
          {JSON.stringify(jsonLd.length === 1 ? jsonLd[0] : jsonLd)}
        </script>
      )}
    </Helmet>
  );
}

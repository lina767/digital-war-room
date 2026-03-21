/**
 * Documentation hub deep links. Legacy routes `/how-it-works`, `/methodology`, `/sources`
 * redirect here so bookmarks keep working.
 */
export const DOCS_HUB = "/docs/documentation";

export const DOCS_HOW_IT_WORKS = `${DOCS_HUB}?doc=how-it-works`;
export const DOCS_METHODOLOGY = `${DOCS_HUB}?doc=methodology`;
export const DOCS_SOURCE_DIRECTORY = `${DOCS_HUB}?doc=source-directory`;

/** Anchor for the dashboard reading guide (slug from DocsArticle heading). */
export const DOCS_DASHBOARD_GUIDE_HASH = "#how-to-read-the-dashboard";

export const DOCS_HOW_IT_WORKS_DASHBOARD_GUIDE = `${DOCS_HOW_IT_WORKS}${DOCS_DASHBOARD_GUIDE_HASH}`;

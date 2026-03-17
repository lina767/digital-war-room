# Discoverability & SEO

Steps to make the repo and site discoverable in search engines and AI platforms.

---

## 0. Prerender (SEO for crawlers)

Crawlers need HTML body content; the SPA only serves a shell from the server. The repo uses **prerender** (Puppeteer) to generate static HTML per route at build time. Vercel’s build environment does not provide Chrome, so prerender runs in **GitHub Actions** and the result is deployed as a prebuilt output.

- **Workflow:** [`.github/workflows/prerender-and-deploy.yml`](../.github/workflows/prerender-and-deploy.yml) runs on push to `main` (and manual dispatch).
- **Build job:** Installs Puppeteer deps, runs `ENABLE_PRERENDER=1 npm run build`, uploads `dist/`.
- **Deploy job:** Builds `.vercel/output` from `dist/` and runs `vercel deploy --prebuilt --prod`. Runs only if `VERCEL_TOKEN` is set.

**Secrets (for deploy job):** In repo **Settings → Secrets and variables → Actions**, add:

- `VERCEL_TOKEN` — from [Vercel Account → Tokens](https://vercel.com/account/tokens)
- `VERCEL_ORG_ID` — from Project Settings → General (or `vercel link` then `.vercel/project.json`)
- `VERCEL_PROJECT_ID` — same place

If these are not set, the workflow still runs the **build** (and you can download the `dist` artifact); only the **deploy** step is skipped.

---

## 1. GitHub Repo (Manual)

### Topics

In the repo **About** section (click the gear next to "About"), add **Topics**:

- `osint`
- `geopolitical-risk`
- `intelligence`
- `multi-agent`
- `fastapi`
- `react`
- `conflict-monitoring`
- `ai-agents`
- `open-source-intelligence`

### Website URL

In repo **Settings → General**, set **Website** to:

- `https://digital-war-room.com`

(Not the Vercel subdomain; use the custom domain so authority is not split.)

---

## 2. Google Search Console & Bing Webmaster (Manual)

After go-live:

1. **Google Search Console**
   - Add property for `https://digital-war-room.com` (domain or URL-prefix).
   - Verify ownership (e.g. via the existing `google-site-verification` meta tag in `index.html`).
   - Submit sitemap: `https://digital-war-room.com/sitemap.xml`.

2. **Bing Webmaster Tools**
   - Add the site and verify.
   - Submit the same sitemap URL.

Bing is important for ChatGPT’s web search; GSC for Google and many AI indexers.

---

## 3. Launch Checklist (Product Hunt, HN, Reddit)

When the repo and site are ready:

- [ ] **Product Hunt** — Submit Digital War Room (link to repo and digital-war-room.com).
- [ ] **Hacker News** — Post as **Show HN: Digital War Room – AI-powered OSINT platform** with short pitch and link.
- [ ] **Reddit** — Post in r/OSINT, r/geopolitics, r/machinelearning (follow each sub’s rules; avoid spam).

Use copy from `docs/social-assets/templates/` (e.g. LinkedIn, X, Reddit templates) for consistent messaging. These platforms generate backlinks that help both search engines and AI citation.

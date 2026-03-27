# Attention playbook — Digital War Room

This playbook is for **building audience and credibility** before packaging a commercial offer. It aligns with the product surfaces already in the repo: **[Live dashboard](/app/dashboard)** (primary), [Demo](/demo) (zero-setup snapshot), [Daily briefing](/daily-briefing), [Docs hub](/docs/documentation), [Blog](/blog), and [Newsletter](/newsletter).

## One-line narrative (shareable)

**Digital War Room is an AI-native OSINT project that fuses fragmented conflict signals into one visual picture—escalation score, theater context, and BLUF-style briefings—with methodology and sources you can inspect.**

Use this when pitching the project in bios, threads, and README intros.

**Pinned in the repo:** the same string is the single source of truth in code as `PINNED_ONE_LINER` in [`src/lib/seoCopy.ts`](../src/lib/seoCopy.ts). Site meta (`index.html`, `app/index.html`), Open Graph/Twitter, JSON-LD, PWA `manifest.json`, dashboard SEO description, and [`README.md`](../README.md) are aligned to it.

### Social bios (copy-paste)

- **Full:** the bold one-liner above (LinkedIn long bio, README, PR descriptions).
- **Short (~160 chars):** use `PINNED_ONE_LINER_SOCIAL_SHORT` from `src/lib/seoCopy.ts` — or paste:  
  `Digital War Room — AI-native OSINT: fuse open conflict signals into one visual picture + BLUF briefings. Inspectable methodology · https://digital-war-room.com`

## Audience ladder

Design content for each step. You do **not** need a paid product for steps 1–4.

| Stage | Who | Goal | Typical CTAs |
| ----- | --- | ---- | ------------ |
| 1. Broad reach | Geopolitics-curious, tech Twitter/LinkedIn, Reddit, HN-style readers | Spark curiosity | Strong visual + one-liner + link to **live dashboard** (or `/demo` if zero-setup matters) |
| 2. Try | OSINT hobbyists, students, journalists | Low-friction proof | **`/app/dashboard`** for full experience; `/demo` or short GIF when setup must be zero |
| 3. Trust | Analysts, researchers, skeptical AI folks | Show rigor | Methodology, source directory, agent docs |
| 4. Subscribe | People who want rhythm | Capture email | `/newsletter` |
| 5. Niche depth | Pro intel/risk/editorial (later) | Deeper relationship | GitHub issues, blog deep-dives, API docs |

**Primary attention ICP (now):** OSINT builders, geopolitics + AI-interested technical audiences, and editorial/research people who share tools and methods.

**Secondary (later commercial signal):** Risk desks and consultancies—follow for credibility, not as the first viral lever.

## Distribution assets (use what exists)

| Asset | Path / location | Best for |
| ----- | --------------- | -------- |
| **Live dashboard** | `/app/dashboard` | **Default share target:** full map, agents, ticker, live feel |
| Curated demo snapshot | `/demo` | Cold traffic when you need a historical snapshot with no backend friction |
| Daily briefing | `/daily-briefing` | Recurring format: PDF export, share link, newsletter fodder |
| Documentation hub | `/docs/documentation` | Skeptics, builders, methodology citations |
| Blog | `/blog` | Longer narratives, release notes, analysis explainers |
| Newsletter | `/newsletter` | Audience capture without a product SKU |
| Repository | GitHub | Stars, issues, “built in public” credibility |

**Tip:** Every public post should point to **one** primary destination (usually **live dashboard** or daily briefing; use `/demo` only when zero-setup beats fidelity), not every URL at once.

## Content engine (repeatable loop)

A sustainable rhythm beats one-off launches. Example **weekly** loop:

1. **Ship or note one concrete change** (agent tweak, UI fix, source, doc)—even small.
2. **One “show” artifact:** screenshot, 30–60s silent GIF/video, or bullet thread of what changed.
3. **One “explain” artifact:** short blog or doc section—why it matters for OSINT or escalation readouts.
4. **Cross-post** the hook to your main channels; deep link to **live dashboard** or briefing (demo when appropriate).
5. **Newsletter (if you send):** recap + link to the same canonical page.

**Content pillars**

- **Transparency:** methodology, limits of open sources, confidence language.
- **Build in public:** architecture choices, agent pipeline, failures and retries.
- **Theater insight:** one focused conflict readout (avoid unfounded predictions—frame as “what open sources show today”).
- **Interface:** why BLUF + map + multi-agent fusion is the thesis.

## Credibility signals (make skepticism a feature)

Lean into what the codebase already supports:

- **Source directory and methodology** in the docs hub—cite them in posts.
- **Agent monitor** (`/app/monitoring`) for “this is a real pipeline, not a single prompt” stories.
- **Data quality / confidence** language in UI and demo snapshot—show you know the difference between signal and hype.
- **Open source (MIT)** and clear privacy/legal pages for trust with technical audiences.

**Avoid:** sounding like a finished classified product or guaranteed forecasts. **Prefer:** “open-source, multi-stream fusion with explicit limitations.”

## 30-day starter checklist

- [ ] Pin the one-liner narrative in README, site meta, and your social bios.
- [ ] Post 2–3 times per week: **dashboard** link or visual, demo when zero-setup helps, or doc excerpt.
- [ ] Publish one longer piece (blog or doc update) on methodology or one agent family.
- [ ] Send or schedule one newsletter that points to `/daily-briefing` or **`/app/dashboard`** (or `/demo` if you stress no-setup).
- [ ] Reply to comments with docs links (source directory, how-it-works) when challenged.

## Related docs

- [Project documentation](PROJECT-DOCUMENTATION.md) — technical index
- [How it works](how-it-works.md) — product behavior
- [Methodology](methodology.md) — scoring and framework notes
- [Source directory](source-directory.md) — provider transparency
- [Newsletter spec](NEWSLETTER-SPEC.md) — email flow

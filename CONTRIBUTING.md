# Contributing to Digital War Room

Thanks for your interest. Here’s how to get started and how to report issues.

## How to run locally

1. **Frontend**
   - From the repo root: `npm install` then `npm run dev`
   - App runs at `http://localhost:8080` by default
   - Set `VITE_API_URL` in a `.env` file if you want to talk to a deployed backend

2. **Backend**
   - See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for running the FastAPI app (e.g. `uvicorn main:app` from `backend/`) and required env vars
   - Optional API keys per agent are documented in [docs/API-KEYS.md](docs/API-KEYS.md)

## Where to find docs

- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — Deploy checklist (Vercel, Railway), env vars, custom domain
- **[docs/API-KEYS.md](docs/API-KEYS.md)** — Backend environment variables and API keys
- **[docs/social-assets/one-pager.md](docs/social-assets/one-pager.md)** — Architecture, agents, design decisions

## How to report bugs

Open a [GitHub Issue](https://github.com/lina767/digital-war-room/issues) and include:

- What you did (e.g. “Clicked Run Analysis on dashboard”)
- What you expected vs what happened
- Browser and OS (if frontend) or environment (if backend)
- Any error messages or console output

## Suggesting features

Feature ideas and improvement suggestions are welcome as [GitHub Issues](https://github.com/lina767/digital-war-room/issues). Use the “Feature request” template if available, or describe the use case and desired behavior.

# Digital War Room

AI-powered OSINT intelligence platform — multi-agent system monitoring global conflicts across GEOINT, SIGINT, SOCMINT, FININT & TECHINT.

## Tech Stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui
- **Backend:** Python 3, FastAPI, LangChain/LangGraph
- **Payments:** Stripe
- **Analytics:** Vercel Analytics

## Getting Started

```sh
# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend runs on `http://localhost:8080` by default.

### Environment Variables

Set the following in a `.env` file in the project root:

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | Backend API URL (e.g. Railway); **Pflicht** für Deploy |

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start dev server |
| `npm run build` | Production build |
| `npm run preview` | Preview production build |
| `npm run lint` | Run ESLint |
| `npm run test` | Run tests |

## Deployment

1. Set environment variables in your hosting platform (Vercel, Cloudflare Pages, etc.)
2. Build command: `npm run build`
3. Output directory: `dist`

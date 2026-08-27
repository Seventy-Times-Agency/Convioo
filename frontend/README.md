# Leadgen Web (Next.js)

Frontend for the Leadgen product, deployed to Vercel. Talks to the
FastAPI backend on Railway over HTTPS.

## Local dev

```bash
cd frontend
npm install
cp .env.local.example .env.local
# edit NEXT_PUBLIC_API_URL to point at your Railway deploy
npm run dev
```

Open http://localhost:3000 — you should see a green "backend healthy"
badge if `/health` on the Railway URL is reachable.

## Environment variables

| Var | Where it's set | Value |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | local (`.env.local`) + Vercel project settings | e.g. `https://leadgen-production.up.railway.app` |

`NEXT_PUBLIC_*` vars are embedded into the client bundle at build time.
No secrets here — the `X-API-Key` for write endpoints never lives in
the frontend; the user pastes it into the dashboard (coming next).

## Deploying to Vercel

1. Log in to [vercel.com](https://vercel.com) with your GitHub account.
2. **Add New… → Project → Import Git Repository** → pick the
   `Seventy-Times-Agency/Leadgen` repo.
3. In the import dialog, set **Root Directory** to `frontend`.
4. Framework preset autodetects **Next.js** — leave defaults.
5. Add env var `NEXT_PUBLIC_API_URL` = your Railway URL
   (you can see it in Railway → Settings → Domains).
6. Deploy. First build takes ~1 minute.
7. Vercel gives you a `*.vercel.app` URL. Copy it.
8. Back in Railway → Variables, set
   `WEB_CORS_ORIGINS` = `https://your-app.vercel.app`
   so the browser can hit the API without CORS errors.

That's it. Every `git push` to `main` triggers both Railway (backend)
and Vercel (frontend) redeploys independently.

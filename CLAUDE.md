# Convioo — Claude Session Handoff

> Read this first. Don't re-explore from scratch.
> Python package on disk: `src/leadgen/` — stable, don't rename.
> Brand everywhere user-facing: **Convioo**.
> Full audit + per-week fixes: `REVIEW.md`. Ops runbook: `docs/operations.md`.

---

## What this is

B2B lead-generation + lightweight CRM for marketing agencies, sales teams, and small-business founders. User describes a target ("roofing companies in New York") → system pulls from Google Places / OSM / Yelp / Foursquare, scrapes sites, runs Claude scoring, delivers into a full CRM with email outreach, Notion/HubSpot/Pipedrive export, webhooks, and a Zapier app.

---

## Hard constraints — never violate

- **No Russian market.** UA / KZ / EU / US / UK only. No Yandex, amoCRM, Bitrix24, рубли.
- **English-first.** `GooglePlacesCollector` defaults `language="en"`, no region bias.
- **Monetization OFF.** `BILLING_ENFORCED=false`. Don't enable without being asked.
- **No emojis in code/files** unless explicitly requested.

---

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2 async, asyncpg, Postgres (Railway)
- Next.js 14 App Router, Tailwind, TypeScript strict (Vercel)
- Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) for Henry + lead analysis
- Google Places API (New), OSM (Nominatim + Overpass), Yelp Fusion, Foursquare v3
- pytest + pytest-asyncio + aiosqlite, ruff, alembic, arq

---

## Architecture

```
src/leadgen/
  core/services/        # framework-agnostic business logic (incl. health_probes)
  adapters/web_api/     # FastAPI factory + per-domain routes/
    routes/             # 17 routers: auth, leads, teams, integrations, webhooks…
    app.py              # ~5 950 lines — partial split, ~77 inline endpoints left
    csrf.py             # CSRF middleware (Origin/Referer + cookie gate)
  pipeline/search.py    # run_search_with_sinks — canonical entrypoint
  collectors/           # google_places, osm, website (SSRF guard), yelp, foursquare
  analysis/             # ai_analyzer (mixins), henry_core, prompts/, knowledge
  integrations/         # stripe_client, gmail, outlook, hubspot, pipedrive, notion
  db/models/            # 50 migrations, models split by domain
  utils/                # retry_async, spawn (observable tasks), http.request_with_retry
  queue/                # arq + Redis (optional)

frontend/
  app/                  # Next.js App Router, 27 pages, error boundaries
  lib/api/              # per-resource API modules
  lib/mobileNav.ts      # pub/sub for hamburger drawer
  lib/hooks/            # useAbortable for fetch cancellation
  components/billing/   # TrialBanner
```

**Rule:** `core/` and `pipeline/` must not import from `adapters/`. Sinks are the bridge.

---

## Current state (main, after audit + 5 cleanup PRs #106-#110)

### Built and working
- Auth: email+password, httpOnly cookie sessions, recovery flows, account lockout, audit log, **HMAC-keyed session/API-key hashes** with transparent SHA-256 fallback.
- Search: Google + OSM + Yelp + Foursquare, SSE progress with 10-min cap + 15s heartbeat, scope/radius, source toggles, saved + scheduled searches.
- CRM: kanban/list with 200-card pagination, custom statuses, tags, custom fields, activity timeline, tasks, **streaming CSV export**, threaded XLSX, bulk draft, CSV import, lead segments.
- Outreach: Gmail OAuth send, Outlook OAuth send, reply tracking (arq cron), daily digest.
- Integrations: Notion (public OAuth + DB picker), HubSpot OAuth, Pipedrive OAuth, Zapier app. **Retry/backoff** wrapping Notion / Slack / Stripe / Resend.
- Public API: API keys (`convioo_pk_*`), Bearer auth, `/developers` page.
- Webhooks: full CRUD + test + HMAC-signed delivery + SSRF allow-list on URLs.
- Admin dashboard (`/app/admin`, `users.is_admin` gate).
- Team analytics, RU/UK/EN locales (key parity), onboarding tour.
- Stripe: checkout, portal, webhook handler (plan sync on subscription events).
- **Trial banner**: `/app/*` ≤3 days (yellow) / ≤1 day (red) → `/app/billing`.
- **Mobile responsive**: hamburger drawer + breakpoints across `/app/*`.
- **Landing**: hero + stats + pain/before-after + how + use cases with social proof + FAQ + pricing teaser + CTA.
- Security headers (CSP, HSTS, X-Frame, Permissions-Policy) on both API and Next.js.
- `/health` probes DB + Redis + arq queue depth in parallel, 2s wait_for cap each.
- Sentry: backend + frontend DSN-gated, observable fire-and-forget via `utils.spawn`.
- 50 alembic migrations (incl. 0049: 33 FK indexes + `LOWER(email)` unique + JSON→JSONB), 398 pytest cases.

### NOT built yet (priority order)
| P | Task |
|---|------|
| P1 | Finish `app.py` split — ~77 inline endpoints still in 5 950 lines. One slice done (leads/archive); next: rest of `/api/v1/leads/*`, `/api/v1/integrations/{notion,hubspot,pipedrive}`, `/api/v1/searches/*` SSE, OAuth callbacks. |
| P1 | Telegram bot v2 — no code; must call `run_search_with_sinks`, new adapter under `adapters/telegram_v2/`. |
| P1 | k6 load test on a staging environment — 200 RPS sustained on `/login`, `/leads` list, SSE, CSV export. |
| P2 | Real staging environment on Railway (currently only PR-preview). |
| P2 | Sentry alerting rules (new issue / >5 events/hour → Slack). |
| P3 | Make.com modules (Zapier is done). |
| P3 | Two-way Notion sync (OAuth done, sync not). |
| P3 | Retry/backoff for HubSpot + Pipedrive — they have custom `_request` with 429 handling; merging strategies safely is a careful PR. |

---

## Deployment

### Railway (backend)
- Build: `Dockerfile` → `entrypoint.sh` → `alembic upgrade head` → `python -m leadgen`
- Health: `GET /health` returns `{status, db, redis, queue_depth, commit}`
- Required env: `DATABASE_URL`, `GOOGLE_PLACES_API_KEY`, `ANTHROPIC_API_KEY`, `AUTH_JWT_SECRET`, `FERNET_KEY`, `PUBLIC_APP_URL`, `WEB_CORS_ORIGINS`
- All other env vars in `.env.example` — copy comments for Railway Variables
- **Never put `*` in `WEB_CORS_ORIGINS`** — the app raises on startup; CSRF middleware requires explicit allow-list.

### Vercel (frontend)
- Project: `convioo-web` (`prj_awuIaLDfkCfaOqfBQM5b8K7pDE9u`), Root: `frontend/`
- `NEXT_PUBLIC_API_URL` must point to Railway public URL
- Auto-deploys on push to main

---

## Local dev

```bash
# Backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill DATABASE_URL + GOOGLE_PLACES_API_KEY + ANTHROPIC_API_KEY
alembic upgrade head
python -m leadgen       # FastAPI on :8080

# Tests
pytest -q && ruff check src tests

# Frontend
cd frontend && npm install
cp .env.local.example .env.local  # set NEXT_PUBLIC_API_URL=http://localhost:8080
npm run dev             # localhost:3000
```

---

## Where to look for each task

| Task | File |
|------|------|
| New API endpoint | `adapters/web_api/routes/` (or `app.py` if domain not split yet) |
| AI prompt | `analysis/prompts/` or `analysis/ai_analyzer.py` |
| Google Places query | `collectors/google_places.py` |
| New DB column | new migration in `alembic/versions/` + `db/models/` |
| Frontend page | `frontend/app/<route>/page.tsx` |
| New integration | `integrations/<name>.py` + retry via `utils.http.request_with_retry` + endpoint in `routes/` |
| Fire-and-forget background task | wrap with `utils.spawn(coro, name=...)` so failures go to Sentry |
| HTTP outbound with retry | `from leadgen.utils.http import request_with_retry` |
| SSRF / URL allow-list | `from leadgen.collectors.website import assert_public_url` |
| Telegram bot (future) | `adapters/telegram_v2/` — build sinks, call `run_search_with_sinks` |
| Operational runbook | `docs/operations.md` |
| Full audit history | `REVIEW.md` |

---

## Common gotchas

1. **ERESOLVE on Vercel** → pin `eslint` to `^8.57` (clashes with `eslint-config-next@14`).
2. **JSONB/UUID in tests** → `_JSONB`/`_UUID` TypeDecorators in `db/models/base.py` switch to JSON/CHAR on SQLite.
3. **`FERNET_KEY` must be set in prod** — without it Notion/OAuth tokens reset on every restart.
4. **`AUTH_JWT_SECRET` rotation** — invalidates the HMAC token lookups; existing sessions/API keys fall back to legacy SHA-256 hash for one more read, then are rehashed. Don't rotate without a smoke window.
5. **`PUBLIC_APP_URL` must be set** — email links use it; default is `http://localhost:3000`.
6. **`BILLING_ENFORCED`** — leave `false` until Stripe is smoke-tested with live keys.
7. **`WEB_CORS_ORIGINS` = `*` will crash startup** — CSRF middleware needs an explicit list.
8. **`app.py` is 5 946 lines** — when adding endpoints to already-split domains, use `routes/*.py`; for new domains, create a new router file and register it in `app.py` (the `include_router` cascade is near line 4990).
9. **Migration 0049 dedup is irreversible** — the partial unique on `LOWER(email)` ran a one-way nullification for duplicates. Don't downgrade past it on a populated DB.

---

## Style notes (user preferences)

- Russian-language conversation. Direct answers only — no filler.
- After every push: state the commit SHA and how to verify deploy (`curl /health`).
- He's on Vercel MCP — use `mcp__5c6f7315-…__*` tools to debug deploys without screenshots.
- No Railway MCP — ask him to share logs if needed.
- He likes squash merges to main, draft PRs first, mark ready when CI is green.

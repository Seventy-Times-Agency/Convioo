# Convioo — Claude Session Handoff

> Read this first. Don't re-explore from scratch.
> Python package on disk: `src/leadgen/` — stable, don't rename.
> Brand everywhere user-facing: **Convioo**.

---

## What this is

B2B lead-generation + lightweight CRM for marketing agencies. User describes a target ("roofing companies in New York") → system pulls from Google Places / OSM / Yelp / Foursquare, scrapes sites, runs Claude scoring, delivers into a full CRM with email outreach, Notion/HubSpot/Pipedrive export, webhooks, and a Zapier app.

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
  core/services/        # framework-agnostic business logic
  adapters/web_api/     # FastAPI factory + per-domain routes/
    routes/             # auth, leads, teams, integrations, webhooks, etc.
    app.py              # ~8 500 lines — partial split, still the main file
  pipeline/search.py    # run_search_with_sinks — canonical entrypoint
  collectors/           # google_places, osm, website, yelp, foursquare
  analysis/             # ai_analyzer (mixins), henry_core, prompts/, knowledge
  integrations/         # stripe_client, gmail, outlook, hubspot, pipedrive, notion
  db/models.py          # 38 migrations, all tables
  export/excel.py
  queue/                # arq + Redis (optional)

frontend/
  app/                  # Next.js App Router, 27 pages
  lib/api/              # per-resource API modules (auth, leads, integrations…)
  components/
```

**Rule:** `core/` and `pipeline/` must not import from `adapters/`. Sinks are the bridge.

---

## Current state (branch `claude/project-management-setup-Jfc0o`, ahead of main)

### Built and working
- Auth: email+password, httpOnly cookie sessions, recovery flows, account lockout, audit log
- Search: Google + OSM + Yelp + Foursquare, SSE progress, scope/radius, source toggles, saved + scheduled searches
- CRM: kanban/list, custom statuses, tags, custom fields, activity timeline, tasks, CSV/Excel export, bulk draft, CSV import, lead segments (saved views)
- Outreach: Gmail OAuth send, Outlook OAuth send, reply tracking (arq cron), daily digest
- Integrations: Notion (public OAuth + DB picker), HubSpot OAuth, Pipedrive OAuth, Zapier app
- Public API: API keys (`convioo_pk_*`), Bearer auth, `/developers` page
- Webhooks: full CRUD + test + HMAC-signed delivery
- Admin dashboard (`/app/admin`, `users.is_admin` gate)
- Team analytics, UA + EN locale, onboarding tour
- Stripe: checkout, portal, webhook handler (plan sync on subscription events)
- Sentry: backend + frontend DSN-gated
- 38 alembic migrations, ~390 pytest cases

### NOT built yet (priority order)
| P | Task |
|---|------|
| P1 | Full `app.py` split — still 8 500 lines, only 8 routes moved to `routes/` |
| P1 | Telegram bot v2 — no code; must call `run_search_with_sinks`, new adapter under `adapters/telegram_v2/` |
| P2 | Mobile responsive — `/app/*` all assume desktop widths |
| P2 | i18n completion — strings exist for UA; EN translations half-empty |
| P3 | Make.com modules (Zapier is done) |
| P3 | Two-way Notion sync (OAuth done, sync not) |
| P3 | Billing trial banner — `trial_ends_at` column + ≤3 days warning on `/app` |

---

## Deployment

### Railway (backend)
- Build: `Dockerfile` → `entrypoint.sh` → `alembic upgrade head` → `python -m leadgen`
- Health: `GET /health` returns `RAILWAY_GIT_COMMIT_SHA`
- Required env: `DATABASE_URL`, `GOOGLE_PLACES_API_KEY`, `ANTHROPIC_API_KEY`, `AUTH_JWT_SECRET`, `FERNET_KEY`, `PUBLIC_APP_URL`, `WEB_CORS_ORIGINS`
- All other env vars in `.env.example` — copy comments for Railway Variables

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
| New DB column | new migration in `alembic/versions/` + `db/models.py` |
| Frontend page | `frontend/app/<route>/page.tsx` |
| New integration | `integrations/<name>.py` + endpoint in `routes/` |
| Telegram bot (future) | `adapters/telegram_v2/` — build sinks, call `run_search_with_sinks` |

---

## Common gotchas

1. **ERESOLVE on Vercel** → pin `eslint` to `^8.57` (clashes with `eslint-config-next@14`).
2. **JSONB/UUID in tests** → `_JSONB`/`_UUID` TypeDecorators in `db/models.py` switch to JSON/CHAR on SQLite.
3. **`FERNET_KEY` must be set in prod** — without it Notion/OAuth tokens reset on every restart.
4. **`PUBLIC_APP_URL` must be set** — email links use it; default is `http://localhost:3000`.
5. **`BILLING_ENFORCED`** — leave `false` until Stripe is smoke-tested with live keys.
6. **app.py is 8 500 lines** — when adding endpoints to already-split domains, use `routes/*.py`; for new domains, create a new router file and register it in `app.py`.

---

## Style notes (user preferences)

- Russian-language conversation. Direct answers only — no filler.
- After every push: state the commit SHA and how to verify deploy (`curl /health`).
- He's on Vercel MCP — use `mcp__5c6f7315-…__*` tools to debug deploys without screenshots.
- No Railway MCP — ask him to share logs if needed.

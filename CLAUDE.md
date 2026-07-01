# Convioo — Claude Session Handoff

> Read this first. Don't re-explore from scratch.
> Python package on disk: `src/leadgen/` — stable, don't rename.
> Brand everywhere user-facing: **Convioo**.
> **Product roadmap, code-verified feature status (BUILT/PARTIAL/MISSING) & the
> 5-wave build plan live in `ROADMAP.md` — read it before planning any feature
> work.** Deep 15-agent audit: `AUDIT_2026-06-26.md`.

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
  core/services/        # framework-agnostic business logic (sinks protocols here)
  adapters/web_api/     # FastAPI factory + per-domain routes/
    routes/             # 29 files — fully split, app.py is 411 lines (router registrations only)
    app.py              # thin shell, ~411 lines
  adapters/telegram_v2/ # Telegram bot v2: api.py, bot.py, sinks.py
  pipeline/search.py    # run_search_with_sinks — canonical entrypoint
  collectors/           # google_places, osm, website, yelp, foursquare
  analysis/             # ai_analyzer (mixins), henry_core, prompts/, knowledge
  integrations/         # stripe_client, gmail, outlook, hubspot, pipedrive, notion, slack, sheets
  db/models.py          # 56 migrations, all tables
  export/excel.py
  queue/                # arq + Redis (optional)

frontend/
  app/                  # Next.js App Router, 15+ pages under app/app/
  lib/api/              # per-resource API modules (auth, leads, integrations…)
  components/
```

**Rule:** `core/` and `pipeline/` must not import from `adapters/`. Sinks are the bridge.

---

## Current state (as of 2026-06-25, main = 76708de)

### Built and working
- Auth: email+password, httpOnly cookie sessions, recovery flows, account lockout, audit log, CSRF protection, CSP headers
- Search: Google + OSM + Yelp + Foursquare, SSE progress, scope/radius, source toggles, saved + scheduled searches
- CRM: kanban/list, custom statuses, tags, custom fields, activity timeline, tasks, CSV/Excel export, bulk draft, CSV import, lead segments (saved views), streaming exports
- Outreach: Gmail OAuth send, Outlook OAuth send, reply tracking (arq cron), daily digest, email sequences, deliverability checker, recipient suppression / do-not-contact list, one-click unsubscribe (RFC 8058 List-Unsubscribe headers + footer + public `/api/v1/unsubscribe/{token}`), GDPR lead-subject erasure (`POST /api/v1/leads/erase-by-email`)
- Integrations: Notion (public OAuth + DB picker + **two-way sync**), HubSpot OAuth, Pipedrive OAuth, Zapier app, **Make.com modules**, Slack webhook, Google Sheets
- Public API: API keys (`convioo_pk_*`), Bearer auth, `/developers` page
- Webhooks: full CRUD + test + HMAC-signed delivery (token hashes stored, not plaintext)
- Admin dashboard (`/app/admin`, `users.is_admin` gate, bootstrap via env)
- Team analytics, UA + EN + RU locale (full i18n coverage), onboarding tour
- Stripe: checkout, portal, webhook handler (plan sync on subscription events), **trial banner** (`trial_ends_at`, ≤3-day warning)
- Sentry: backend + frontend DSN-gated
- Mobile responsive (mobile sidebar drawer, Topbar adapts)
- **Telegram bot v2**: `adapters/telegram_v2/` — webhook endpoint, account linking via token, `/search niche in region`, `TelegramProgressSink` + `TelegramDeliverySink`, webhook secret validation
- OAuth state PKCE, SSRF guard on outbound HTTP, `utils.spawn`, `utils.http.request_with_retry`
- Health probe: `GET /health` (db + redis + queue checks). Set it as the **API service's** Healthcheck Path in the Railway dashboard, NOT in `railway.json` — that file is shared with the arq WORKER service, which has no HTTP server and would fail a `/health` check on every deploy.
- 56 alembic migrations, 556 pytest cases

### NOT built yet / what's next
**See `ROADMAP.md` for the full code-verified feature map (BUILT/PARTIAL/MISSING)
and the prioritized 5-wave build plan — that is the source of truth for what to
build next.** Quick highlights of large gaps: self-learning scoring, AI reply
classification, deal copilot, multi-channel outreach, cost cap, pipeline
forecast, two-way HubSpot/Pipedrive pull, Chrome extension. Recently shipped this
line of work: connectors marketplace, suppression/do-not-contact + one-click
unsubscribe, GDPR lead erasure, SEO infra,
security bumps — see `ROADMAP.md` status map.

---

## Deployment

### Railway (backend)
- Build: `Dockerfile` → `entrypoint.sh` → `alembic upgrade head` → `python -m leadgen`
- Health: `GET /health` returns `RAILWAY_GIT_COMMIT_SHA`
- Required env: `DATABASE_URL`, `GOOGLE_PLACES_API_KEY`, `ANTHROPIC_API_KEY`, `AUTH_JWT_SECRET`, `FERNET_KEY`, `PUBLIC_APP_URL`, `WEB_CORS_ORIGINS`
- All other env vars in `.env.example` — copy comments for Railway Variables
- **Telegram production setup** (user action required): set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_WEBHOOK_SECRET`, then register the webhook:
  ```
  curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
    -d "url=$PUBLIC_APP_URL/api/v1/telegram/webhook" \
    -d "secret_token=$TELEGRAM_WEBHOOK_SECRET"
  ```

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
| New API endpoint | `adapters/web_api/routes/<domain>.py` — all domains are split |
| AI prompt | `analysis/prompts/` or `analysis/ai_analyzer.py` |
| Google Places query | `collectors/google_places.py` |
| New DB column | new migration in `alembic/versions/` + `db/models.py` |
| Frontend page | `frontend/app/<route>/page.tsx` |
| New integration | `integrations/<name>.py` + endpoint in `routes/` |
| Telegram bot | `adapters/telegram_v2/` — bot.py (commands), sinks.py (progress/delivery) |
| Progress/delivery protocols | `core/services/sinks.py` — ProgressSink, DeliverySink, NullSink |

---

## Common gotchas

1. **ERESOLVE on Vercel** → pin `eslint` to `^8.57` (clashes with `eslint-config-next@14`).
2. **JSONB/UUID in tests** → `_JSONB`/`_UUID` TypeDecorators in `db/models.py` switch to JSON/CHAR on SQLite.
3. **`FERNET_KEY` must be set in prod** — without it Notion/OAuth tokens reset on every restart.
4. **`PUBLIC_APP_URL` must be set** — email links use it; default is `http://localhost:3000`.
5. **`BILLING_ENFORCED`** — leave `false` until Stripe is smoke-tested with live keys.
6. **`WEB_CORS_ORIGINS='*'`** breaks startup — must be a comma-separated list of origins.
7. **`AUTH_JWT_SECRET` rotation** is irreversible — all existing sessions invalidate on change.
8. **StaticPool in tests** — tests that nest `session_factory()` calls need `StaticPool` + `check_same_thread=False` (see `test_notion_twoway_sync.py` fixture pattern).
9. **`get_settings.cache_clear()`** — call before and after `monkeypatch.setenv` in tests that toggle env vars.
10. **Migration 0049** — dedup operation is irreversible.

---

## Style notes (user preferences)

- Russian-language conversation. Direct answers only — no filler.
- After every push: state the commit SHA and how to verify deploy (`curl /health`).
- He's on Vercel MCP — use `mcp__5c6f7315-…__*` tools to debug deploys without screenshots.
- No Railway MCP — ask him to share logs if needed.

# Leadgen — Handoff for the Next Claude Session

> Read this file first. Don't re-explore the repo from scratch — the
> code below is current as of commit `e732014` and tells you what's
> here, where it lives, what's done, what's next, and what NOT to do.

---

## 1. What this is

A B2B lead-generation bot for marketing agencies. User describes their
target ("roofing companies in New York"); the system pulls matching
companies from Google Places, scrapes their websites and reviews,
runs every lead through Claude for a personalized score + outreach
advice, and delivers a report + Excel.

- **Telegram bot** — fully built and live (this is the production surface today)
- **Web app (Next.js on Vercel)** — landing page deployed; dashboard / search flow / SSE progress NOT yet built
- **Backend (Python FastAPI + aiogram)** — runs on Railway

User is the founder of a Ukrainian agency, building this primarily for
his own team's use, then planning to release publicly.

---

## 2. Hard constraints — DO NOT VIOLATE

These are user preferences he's restated multiple times. Don't suggest
otherwise unless he explicitly asks.

- **NO Russian market** — UA / KZ / СНГ-без-РФ / EU / US / UK only.
  Do not propose Yandex Maps, 2GIS-as-Russia-tool, amoCRM, Bitrix24,
  YooKassa, рубли. He's Ukrainian and politically opposed to that
  market. (2GIS is OK to mention because their non-RU coverage is
  good — Almaty, Astana, Kyiv, Cyprus, parts of EU — but de-emphasize.)
- **English-first / multilingual** — `Settings.web_api_key` defaults
  for Google Places are `language="en"`, `region_code=None` (no bias).
  Do not regress to Russian defaults.
- **Monetization is OFF** — `Settings.billing_enforced` defaults to
  `False`. He's still iterating personally, no quota gating. Don't
  enable enforcement without him asking. The infrastructure (counters,
  limits, Stripe planning) is in place for later.
- **Push to `main`** — he asked for one branch only. No long-lived
  feature branches. Keep commits small and meaningful.
- **No emojis in code/files** unless he explicitly asks. Bot strings
  in handlers DO use emoji because that's user-facing copy he likes;
  Python comments / docstrings stay clean.

---

## 3. Architecture (after Stage 2 refactor)

```
src/leadgen/
  core/services/          ← framework-agnostic business logic
    billing_service.py    ← atomic quota, race-safe, has BILLING_ENFORCED kill switch
    profile_service.py    ← User profile patch/reset
    sinks.py              ← ProgressSink / DeliverySink Protocols + NullSink
    progress_broker.py    ← in-process pub/sub for SSE; BrokerProgressSink

  adapters/               ← thin client-specific layers
    telegram/
      sinks.py            ← TelegramProgressSink + TelegramDeliverySink
    web_api/
      app.py              ← FastAPI factory (/health, /metrics, /api/v1/*)
      auth.py             ← X-API-Key header check
      schemas.py          ← Pydantic I/O models

  pipeline/
    search.py             ← run_search (Telegram entry) + run_search_with_sinks (pure)
    enrichment.py         ← website fetch + Google details + AI analysis
    progress.py           ← ProgressReporter (Telegram message edits, throttled)
    recovery.py           ← Marks stale "running" queries failed on startup

  collectors/
    google_places.py      ← Places API (New) — defaults language="en", no region bias
    website.py            ← Generic site scraper, filters generic emails

  analysis/
    ai_analyzer.py        ← Claude Haiku wrapper. Has parse_name/age/biz/region,
                            normalize_profession, extract_search_intent, plus the
                            main analyze_lead + base_insights. Heuristic fallbacks
                            for every parser when no API key.
    aggregator.py         ← BaseStats from enriched leads

  bot/
    handlers.py           ← ALL aiogram handlers (1200+ lines, growing). Onboarding,
                            search flow, profile edit, /reset, /diag.
    main.py               ← Bot bootstrap: DB init, polling, FastAPI on $PORT
    middlewares.py        ← DbSessionMiddleware (registered for BOTH message and
                            callback events — critical, see commit f161f9e)
    diagnostics.py        ← /diag — live integration smoke tests
    keyboards.py, states.py

  db/
    models.py             ← SQLAlchemy: User, SearchQuery, Lead, UserSeenLead,
                            Team, TeamMembership. JSONB/UUID have TypeDecorator
                            wrappers so unit tests can use SQLite.
    session.py            ← Lazy engine + lazy session_factory function (NOT instance)

  queue/                  ← Optional arq + Redis. Activates when REDIS_URL is set.
    enqueue.py, worker.py

  web/                    ← Deprecated forwarding alias for create_app
  utils/                  ← rate_limit, secrets sanitizer, retry, Prometheus metrics

frontend/                 ← Next.js 14 (App Router) + Tailwind, dark theme.
                            Currently only landing page with HealthBadge.
                            Vercel project: leadgen-web.

alembic/versions/         ← 5 migrations, latest is 20260423_0005_teams_and_memberships
```

### Key architectural rule

**`core/` and `pipeline/` MUST NOT import from `bot/` or
`adapters/`.** They're framework-agnostic. The TelegramProgressSink
and TelegramDeliverySink translate aiogram-specific operations into
the abstract sink protocols. Web adapter does the same with FastAPI +
SSE broker.

`run_search_with_sinks(query_id, progress, delivery, user_profile)` is
the canonical entrypoint. The Telegram `run_search` is a thin shim
that builds Telegram sinks and delegates.

---

## 4. Tech stack

- Python 3.12, aiogram 3, FastAPI, SQLAlchemy 2 (async), asyncpg
- Postgres on Railway, optional Redis (not yet provisioned)
- Anthropic Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- Google Places API (New) — Text Search + Place Details
- Next.js 14 App Router on Vercel, Tailwind, TypeScript strict
- pytest + pytest-asyncio + aiosqlite (in-memory DB for unit tests)
- ruff, alembic, prometheus-client, arq

---

## 5. Deployment

### Railway (backend)
- Project name: `leadgen`
- Public URL: `https://leadgen-production-6758.up.railway.app`
- Builds from root `Dockerfile`, runs `entrypoint.sh` which does
  `alembic upgrade head` then `python -m leadgen`
- Runs ONE container with: aiogram polling loop + uvicorn FastAPI on
  `$PORT` + Postgres queries. No worker yet.
- Required env vars (already set, except where noted):
  `BOT_TOKEN`, `DATABASE_URL`, `GOOGLE_PLACES_API_KEY`,
  `ANTHROPIC_API_KEY`, `WEB_API_KEY`, `WEB_CORS_ORIGINS`
- Optional: `REDIS_URL` (queue), `BILLING_ENFORCED=true` (turn quotas
  back on), `RAILWAY_GIT_COMMIT_SHA` (auto-injected, used in /health)

### Vercel (frontend)
- Project name: `leadgen-web` (id `prj_awuIaLDfkCfaOqfBQM5b8K7pDE9u`)
- Public URL: `https://leadgen-seven-lac.vercel.app`
- Root Directory: `frontend` (NOT repo root — repo root is Python)
- Env: `NEXT_PUBLIC_API_URL=https://leadgen-production-6758.up.railway.app`
- Auto-deploys on push to main
- MCP integration: scoped to team `team_CEe8uMizl6fpm2dRmu8AUXOF`,
  use those tools to read deployments / logs without bothering the user

---

## 6. Current state (as of e732014)

### Working in production
- Bot full onboarding (6 steps with AI free-form parsing on every field)
- `/profile` view + per-field edit + `/reset`
- `/diag` integration health check
- Search flow: free-form niche → AI-extracted niche picker → region → confirm → live progress bar → stats + insights + top-5 cards + Excel
- Cross-run dedup via `user_seen_leads`
- Bulletproof delivery (each step isolated)
- 10-min hard timeout on searches
- Auto-cleanup of Lead rows after delivery (keeps SearchQuery summary)
- Atomic quota counter (currently NOT enforcing because BILLING_ENFORCED=false)
- Partial unique index against parallel in-flight searches
- Per-user rate limit (5 searches/min in memory)
- Prometheus metrics on every terminal branch
- /health + /metrics on FastAPI
- Web landing page on Vercel with green health badge

### Built but not yet user-facing
- Web API endpoints: POST/GET `/api/v1/searches`, GET `/api/v1/searches/{id}/progress` (SSE)
- BrokerProgressSink (in-process pub/sub for SSE)
- BillingService, ProfileService, sink protocols — used by bot, ready for web
- Team/Membership tables (no UI yet)
- arq queue scaffolding (needs Redis)

### NOT built yet (next session likely starts here)
- Web frontend pages beyond landing: login, dashboard, new-search form,
  search-detail-with-SSE
- `GET /api/v1/searches/{id}/leads` endpoint (need this for the web to show results)
- POST `/api/v1/searches` doesn't actually invoke the pipeline yet —
  it creates a row and tries to enqueue (which fails without Redis).
  Need to either enable arq + Redis or spawn `asyncio.create_task` inline.
- `WebDeliverySink` — currently the search auto-deletes leads, so the web
  can't read them after. Either delay cleanup or persist via a delivery sink.
- Real auth (magic link via Resend) — currently single shared API key
- Outreach message generation
- Email/phone/website verification
- Decision-maker discovery (scrape /team /about pages)
- Multi-source collectors (OSM/Foursquare/Yelp/2GIS-non-RU)
- CRM-lite (lead status: new/contacted/replied/closed)
- Stripe / Telegram Stars billing

### IMPORTANT pending design decisions (user has NOT approved)
- Web UI structure (single dashboard vs multi-page, kanban vs list, …)
- Visual style (Linear-like / Vercel-like / colorful)
- Auth method (API key vs magic link vs Telegram login)
- Lead card depth (minimum vs full vs with-outreach)
- Whether to include CRM in v1

**Do not start coding the frontend until user explicitly approves
each of these.** Last session he stopped me mid-typing: "стой я тебе
не говорю чтоб все чтобы ты работал над интерфейсом потому что мы их
ещё пока не утвердили".

---

## 7. Local dev quickstart

```bash
# Backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill BOT_TOKEN, DATABASE_URL, GOOGLE_PLACES_API_KEY, ANTHROPIC_API_KEY
alembic upgrade head
python -m leadgen  # starts bot polling + FastAPI on :8080

# Tests (153 of them, all pass)
pytest -q
ruff check src tests

# Frontend
cd frontend
npm install
cp .env.local.example .env.local  # set NEXT_PUBLIC_API_URL
npm run dev  # localhost:3000
```

---

## 8. Working with the user — style notes

- Russian-language conversation, often imperfect grammar / typos.
  Don't correct him, just understand intent.
- He prefers DIRECT answers. No "great question!" filler. State the
  fix, give 2-3 lines of why.
- Walk him through UI clicks step-by-step when he's stuck on
  Vercel/Railway settings — he is non-technical-enough that "go to
  Settings → Source" needs to be literal click instructions.
- He responds well to visible progress: commit, push, tell him what
  to expect, give him concrete URLs to check.
- After every push, tell him which commit SHA he's looking at and
  how to verify it deployed (commit SHA shows up in `/health` and in
  the bot's startup banner).
- He has Vercel MCP integration granted to you. Use
  `mcp__5c6f7315-…__list_deployments` / `get_deployment_build_logs`
  to debug Vercel deploys without asking him for screenshots.
- He does NOT have a Railway MCP integration. For Railway debugging,
  ask him to share logs or use `/diag` from the bot.

---

## 9. Common gotchas / lessons (sorted by past-pain)

1. **Inline buttons stuck on spinner** → middleware was on
   `dp.message` only. Always register on both `dp.message` AND
   `dp.callback_query`. Fixed in commit f161f9e.
2. **Vercel build fails with ERESOLVE** → `eslint@9` clashes with
   `eslint-config-next@14.x` peer-dep. Pin eslint to `^8.57`.
3. **Search returns weird results (e.g. roofing → university)** →
   `GooglePlacesCollector` had hardcoded `language="ru"` /
   `region_code="RU"`. Now defaults to `en` / unset.
4. **Bot crashes silently on startup** → settings used to be
   instantiated at module-level. Now `get_settings()` is lazy and
   logs the error if env vars missing.
5. **Postgres has tables but alembic_version is empty** →
   `entrypoint.sh` runs `alembic upgrade head`, falls back to
   `alembic stamp head` if upgrade fails, ALWAYS runs `python -m
   leadgen` so the bot at least starts.
6. **Profile edit buttons did nothing for non-text fields** →
   age/business_size handlers needed callback path AND text path.
7. **JSONB / UUID don't work in SQLite** → `_JSONB` and `_UUID`
   TypeDecorator wrappers in `db/models.py` switch to JSON / CHAR(36)
   on SQLite, native types on Postgres. Lets unit tests run with
   `aiosqlite` instead of needing a Postgres container.
8. **API keys leaking in logs** → `utils/secrets.sanitize()` scrubs
   Google/Anthropic/Telegram tokens from any string. Wrap response
   bodies before logging them.
9. **One container, two surfaces** → `bot/main.py` runs uvicorn as
   an asyncio task alongside `dp.start_polling`. Don't try to start
   them in separate processes — Railway one-port limit, simpler ops.
10. **Telegram-side sinks are in `adapters/telegram/sinks.py`,
    NOT in `bot/handlers.py`.** The old `_deliver` function was
    extracted out during Stage 2. Don't put new delivery logic in
    handlers.

---

## 10. Where you should look first depending on the task

| Task | Start here |
|---|---|
| Add a new web API endpoint | `adapters/web_api/app.py` + `schemas.py` |
| Add a new bot command | `bot/handlers.py` (search for existing `@router.message`) |
| Change AI prompt | `analysis/ai_analyzer.py` |
| Change Google Places query shape | `collectors/google_places.py` |
| Change progress / delivery format | `adapters/telegram/sinks.py` (Telegram) or write new sink in `core/services/` |
| Add a new DB column | new alembic migration in `alembic/versions/` + update `db/models.py` |
| Add CI step | `.github/workflows/ci.yml` |
| Frontend page | `frontend/app/<route>/page.tsx` + components in `frontend/components/` |

---

## 11. Last commit

`e732014` — Pin eslint to 8.57 so Vercel npm install resolves peer deps.

Vercel deploy is GREEN (`leadgen-seven-lac.vercel.app`), Railway
deploy is GREEN (`leadgen-production-6758.up.railway.app/health`
returns `{"status":"healthy"}`), CORS is configured, frontend's
HealthBadge shows green. Test count: 153, all pass, ruff clean.

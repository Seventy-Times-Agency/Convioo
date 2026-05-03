# Convioo — Handoff for the Next Claude Session

> Read this file first. Don't re-explore the repo from scratch — the
> code below is current as of `main` after PRs #32-#39 shipped on
> 2026-05-03 (Stripe billing + Gmail OAuth + saved segments +
> saved/scheduled searches + admin dashboard + Yelp + Foursquare +
> per-search source toggles + Sentry). 36 alembic migrations,
> ~340 pytest cases. ``git log -1 main --oneline`` confirms head.
>
> The product was originally codenamed "Leadgen" and the Python package
> on disk is still `src/leadgen/` — don't rename it, the import path is
> stable. The user-facing brand everywhere (frontend, repo, marketing)
> is **Convioo**.

---

## 1. What this is

A B2B lead-generation + lightweight CRM platform for marketing agencies.
User describes their target ("roofing companies in New York"); the
system pulls matching companies from Google Places + OpenStreetMap,
scrapes their websites and reviews, runs every lead through Claude for
a personalized score + outreach advice, then delivers leads into a CRM
with statuses, notes, tasks, activity timeline, custom fields, tags,
outreach drafts, bulk cold-email drafting, Excel/CSV export, and
optional one-click push into the user's Notion database.

- **Web app (Next.js 14 on Vercel)** — the only delivery surface today.
  27 pages, real email/password auth + recovery flows + httpOnly
  cookie sessions, dashboard, search (with niche + city autocomplete,
  scope city/metro/state/country, radius slider) → SSE progress,
  sessions, full CRM (`/app/leads`) with tag chips + bulk draft +
  Notion export, templates, billing UI, team invites, profile,
  settings (security + Notion integration card), public pages
  (pricing/help/changelog/comparison/legal).
- **Backend (Python FastAPI)** — runs on Railway, ~14k LoC,
  36 alembic migrations, ~38 pytest files (340+ test cases).
- **Henry** — in-product AI assistant (Claude Haiku 4.5) used for
  search consult, profile-aware suggestions, per-lead research, weekly
  check-ins, and cold-email drafts. Persona + memory live in
  `analysis/henry_core.py`, `knowledge.py`, `core/services/assistant_memory.py`.

> **Telegram bot was REMOVED** in this branch. Old code lived in
> `src/leadgen/bot/` + `src/leadgen/adapters/telegram/` and is gone.
> The user is rebuilding the bot from scratch later — when that happens,
> a new adapter should plug into the existing `core/services` and call
> `run_search_with_sinks` from `pipeline/search.py`. Do NOT resurrect
> the old aiogram code.

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
- **English-first / multilingual** — `GooglePlacesCollector` defaults
  to `language="en"`, `region_code=None` (no bias). Do not regress to
  Russian defaults. Per-search target languages live on
  `search_queries.target_languages` (migration 0012).
- **Monetization is OFF** — `Settings.billing_enforced` defaults to
  `False`. He's still iterating personally, no quota gating. Don't
  enable enforcement without him asking. The infrastructure (counters,
  limits, Stripe planning) is in place for later.
- **Push to `main`** — he asked for one branch only. No long-lived
  feature branches. Keep commits small and meaningful.
- **No emojis in code/files** unless he explicitly asks. Python
  comments / docstrings stay clean.

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
    web_api/
      app.py              ← FastAPI factory (/health, /metrics, /api/v1/*)
      auth.py             ← X-API-Key header check
      schemas.py          ← Pydantic I/O models
      sinks.py            ← WebDeliverySink (writes broker events for SSE)

  pipeline/
    search.py             ← run_search_with_sinks (pure pipeline) +
                            run_search_with_timeout (wrapper)
    enrichment.py         ← website fetch + Google details + AI analysis
    recovery.py           ← Marks stale "running" queries failed on startup

  collectors/
    google_places.py      ← Places API (New) — defaults language="en", no region bias
    osm.py                ← OpenStreetMap (Nominatim + Overpass), free, EU/UA-strong;
                            auto-queried in parallel when the niche has osm_tags
    website.py            ← Generic site scraper, filters generic emails

  analysis/
    ai_analyzer.py        ← Claude Haiku wrapper, ~2.5k lines. parse_name/age/biz/
                            region, normalize_profession, extract_search_intent,
                            analyze_lead, base_insights, draft_lead_email,
                            research_lead. Heuristic fallbacks for every parser.
    henry_core.py         ← Henry persona + shared chat/consult primitives.
    knowledge.py          ← Static product knowledge fed to Henry's prompts.
    aggregator.py         ← BaseStats from enriched leads.

  core/services/          (cont'd)
    assistant_memory.py   ← Persistent Henry memory per user.
    email_sender.py       ← Outbound transactional email (verification, invites).

  db/
    models.py             ← SQLAlchemy. Tables: User, SearchQuery, Lead,
                            UserSeenLead, Team, TeamMembership, TeamInvite,
                            TeamSeenLead, LeadMark, EmailVerificationToken,
                            AssistantMemory, OutreachTemplate, LeadCustomField,
                            LeadActivity, LeadTask, UserAuditLog. JSONB/UUID
                            have TypeDecorator wrappers so unit tests can use SQLite.
    session.py            ← Lazy engine + lazy session_factory function (NOT instance)

  export/excel.py         ← openpyxl-based styled workbook builder for sessions.
  queue/                  ← Optional arq + Redis. Activates when REDIS_URL is set.
    enqueue.py, worker.py

  web/                    ← Deprecated forwarding alias for create_app
  utils/                  ← rate_limit, secrets sanitizer, retry, Prometheus metrics

frontend/                 ← Next.js 14 App Router, custom design system in
                            `app/globals.css` (ported from prototype). Inter +
                            JetBrains Mono. Dark theme + light theme toggle.
                            i18n via `lib/i18n.tsx`. 24 pages, see section 6.
                            Vercel project name still `leadgen-web` (legacy).

alembic/versions/         ← 21 migrations, latest is
                            20260427_0021_user_audit_logs.
```

### Key architectural rule

**`core/` and `pipeline/` MUST NOT import from `adapters/`.** They're
framework-agnostic. The web adapter (FastAPI + SSE broker) translates
HTTP-specific operations into the abstract sink protocols.

`run_search_with_sinks(query_id, progress, delivery, user_profile)` is
the canonical entrypoint. When the future Telegram bot is rebuilt, it
should also build sinks and call this function — not reimplement
search.

---

## 4. Tech stack

- Python 3.12, FastAPI, SQLAlchemy 2 (async), asyncpg
- Postgres on Railway, optional Redis (not yet provisioned)
- Anthropic Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- Google Places API (New) — Text Search + Place Details
- Next.js 14 App Router on Vercel, Tailwind, TypeScript strict
- pytest + pytest-asyncio + aiosqlite (in-memory DB for unit tests)
- ruff, alembic, prometheus-client, arq

---

## 5. Deployment

### Railway (backend)
- Project name in Railway: `leadgen` (legacy — Railway project not
  renamed when GitHub repo became `Convioo`).
- Public URL: set via Railway service "Public Domain". Old URL was
  `https://leadgen-production-6758.up.railway.app` — verify in Railway
  UI after the rename, the new URL may have changed.
- Builds from root `Dockerfile`, runs `entrypoint.sh` which does
  `alembic upgrade head` then `python -m leadgen`.
- Runs ONE container: uvicorn FastAPI on `$PORT` + Postgres queries.
  When Redis is provisioned, an arq worker runs as a second service.
- Required env vars: `DATABASE_URL`, `GOOGLE_PLACES_API_KEY`,
  `ANTHROPIC_API_KEY`, `WEB_CORS_ORIGINS`, `PUBLIC_APP_URL`,
  `RESEND_API_KEY` (when verification email is enabled),
  `FERNET_KEY` (encrypts Notion + OAuth tokens at rest — MUST be set
  in prod or restarts wipe every saved integration).
- Stripe (P0) — set ALL to enable real billing:
  `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_PRO`,
  `STRIPE_PRICE_ID_AGENCY`, `STRIPE_TRIAL_DAYS=14`. Empty = endpoints
  return 503. Webhook URL to register in Stripe:
  `https://<api-host>/api/v1/billing/webhook`. Subscribe to
  `checkout.session.completed`, `customer.subscription.{created,updated,deleted}`,
  `invoice.payment_{succeeded,failed}`.
- Gmail OAuth (P0) — `GOOGLE_OAUTH_CLIENT_ID`,
  `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`. Empty =
  endpoints return 503. Get from
  https://console.cloud.google.com/apis/credentials with the
  `gmail.send` scope.
- HubSpot OAuth — `HUBSPOT_OAUTH_CLIENT_ID`,
  `HUBSPOT_OAUTH_CLIENT_SECRET`, `HUBSPOT_OAUTH_REDIRECT_URI`. Empty =
  `/api/v1/integrations/hubspot/*` endpoints return 503. Create the
  app at https://app.hubspot.com/developer with the
  `crm.objects.contacts.write` + `.read` scopes; redirect URI must
  match the env value.
- Multi-source: `YELP_API_KEY` (https://docs.developer.yelp.com),
  `FSQ_API_KEY` (https://foursquare.com/developers). Each
  collector skips silently when its key is empty.
- Sentry (T13): `SENTRY_DSN_API` (backend),
  `NEXT_PUBLIC_SENTRY_DSN` (Vercel). Optional source-map upload on
  Vercel: `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT`.
- Optional: `REDIS_URL` (queue), `WEB_API_KEY` (gates SSE),
  `BILLING_ENFORCED=true` (turn quotas back on after Stripe smoke
  test), `RAILWAY_GIT_COMMIT_SHA` (auto-injected, used in /health),
  `SAVED_SEARCH_SCHEDULER=0` (disable in-process scheduler when
  running multiple API replicas without Redis).
- `BOT_TOKEN` is no longer required — Telegram bot was removed.

### Vercel (frontend)
- Project name: `convioo-web` (id `prj_awuIaLDfkCfaOqfBQM5b8K7pDE9u`)
- Public URL: see Vercel UI; production preview pattern is
  `convioo-web-*.vercel.app`. Old `leadgen-seven-lac.vercel.app` may
  still alias for transition — confirm.
- Root Directory: `frontend` (NOT repo root — repo root is Python)
- Env: `NEXT_PUBLIC_API_URL` must point to current Railway public URL.
- Auto-deploys on push to main
- MCP integration: scoped to team `team_CEe8uMizl6fpm2dRmu8AUXOF`,
  use those tools to read deployments / logs without bothering the user

---

## 6. Current state (as of 7afdaee, PR #20)

### Working in production
- **Web app** — only delivery surface. End-to-end flow on Vercel + Railway:
  landing → register/login (email + password) → verify-email →
  onboarding → `/app` dashboard → `/app/search` (Henry chat + SSE
  progress ring) → `/app/sessions[/id]` (lead grid + Excel/CSV export)
  → `/app/leads` (full CRM with kanban/list, filters, search, sort,
  bulk actions, CSV export) → `/app/templates` (outreach library) →
  `/app/import` (CSV bulk import) → `/app/billing` (plan cards, USD)
  → `/app/team` (invites, members, descriptions) → `/app/profile`,
  `/app/settings` (change email/password, language, theme, GDPR
  export/delete, audit log).
- **Public pages** — landing, pricing, help, changelog, comparison
  (`/vs/[competitor]`), legal trio (privacy/terms/cookies).
- **Henry assistant** — persona-driven chat on `/app/search`, weekly
  check-in card on dashboard, per-lead AI research and cold-email
  drafts inside `LeadDetailModal`, persistent memory.
- **Theme + i18n + PWA** — light/dark toggle persisted, language
  switcher, manifest installed.

### Frontend pages (24)
Public: `/`, `/login`, `/register`, `/verify-email/[token]`,
`/join/[token]`, `/onboarding`, `/pricing`, `/help`, `/changelog`,
`/privacy`, `/terms`, `/cookies`, `/vs/[competitor]`.
App (gated by `RequireAuth`): `/app`, `/app/search`, `/app/sessions`,
`/app/sessions/[id]`, `/app/leads`, `/app/templates`, `/app/import`,
`/app/billing`, `/app/team`, `/app/profile`, `/app/settings`.
Public auth recovery: `/forgot-password`, `/reset-password/[token]`,
`/forgot-email`. ``next.config.js`` rewrites ``/api/*`` to the Railway
backend so the auth cookie is first-party.

### Web API (~70 endpoints in `adapters/web_api/app.py`, ~4.5k lines)
Auth: register / login / logout / logout-all / verify-email /
resend-verification / forgot-password / reset-password /
forgot-email / me / sessions list+revoke / recovery-email PATCH.
Login issues an httpOnly+SameSite=Lax cookie (``convioo_session``);
all new endpoints rely on it via ``get_current_user`` dependency.
Account lockout: 10 failed logins → 15 min cooldown + email alert.
New-device login fires ``render_new_device_login_email``.
User: get / patch / change-email / change-password / audit-log /
GDPR-export / GDPR-delete. Canonical paths now live under
``/api/v1/users/me/*``; the legacy ``/api/v1/users/{user_id}/*``
paths return 308 redirects to the ``/me`` equivalent (and 403 when
the path id doesn't match the cookie session, closing the historic
IDOR).
Teams: create / list / get / patch / membership-patch / invites /
invite-accept / invite-preview.
Search: `POST /api/v1/search/consult`, `POST /api/v1/assistant/chat`
(Henry), `POST /api/v1/searches`, `GET /api/v1/searches[?team_id]`,
`GET /api/v1/searches/{id}`, `GET /api/v1/searches/{id}/leads`,
`GET /api/v1/searches/{id}/export.xlsx` (PR #20),
`GET /api/v1/searches/{id}/progress` (SSE).
Leads (CRM): list / patch / get / mark / custom-fields CRUD /
activity / tasks / CSV export / CSV import.
Templates: full CRUD on `/api/v1/templates`.
Tags: full CRUD on `/api/v1/tags`, `PUT /api/v1/leads/{id}/tags` to
assign, `GET /api/v1/leads?tag_id=...` to filter. Bulk draft:
`POST /api/v1/leads/bulk-draft` writes cold-email drafts for up to
20 leads in one shot.
Niche taxonomy: `GET /api/v1/niches?q=&lang=` (public, static
dictionary feeding the search-form combobox; not the same as the
LLM-driven `/users/{id}/suggest-niches`).
Cities catalogue: `GET /api/v1/cities?q=&country=&lang=` (curated
~120 cities feeding the region combobox; pipeline reuses cached
coords to skip Nominatim entirely when a curated city matches).
Stats: `GET /api/v1/stats`, `GET /api/v1/team`,
`GET /api/v1/queue/status`.

### Schema — 26 migrations
0001 initial → 0002 user profile → 0003 demographics → 0004 dedup +
search lock → 0005 teams + memberships → 0006 web source + lead CRM
fields → 0007 last_name → 0008 invites + team-scoped searches →
0009 lead marks + team scoping → 0010 UUID for team tables →
0011 team descriptions + team_seen_leads → 0012 search target
languages → 0013 email + password auth → 0014 pending_email →
0015 UUID for verification tokens → 0016 assistant memories →
0017 widen profession to TEXT → 0018 users.gender → 0019 outreach
templates → 0020 lead custom fields + activity + tasks →
0021 user audit logs → 0022 user_sessions table + users.recovery_email
+ users.failed_login_attempts + users.locked_until →
0023 leads.deleted_at + leads.blacklisted + search_queries.max_results
+ user_seen_leads/team_seen_leads gain phone_e164 + domain_root for
fuzzy dedup → 0024 lead_tags + lead_tag_assignments (user-defined
chip palette per user / team, attached to leads many-to-many) →
0025 user_integration_credentials (Fernet-encrypted Notion token +
config.database_id; per-user, per-provider) →
0026 search_queries.scope + .radius_m + .center_lat/.center_lon
(geo-shape parameters: city/metro/state/country + cached Nominatim
center).

### Web runtime rules
- All searches are web-origin now; lead rows persist forever so the
  CRM keeps history.
- `run_search_job` (arq worker) always uses
  `BrokerProgressSink + WebDeliverySink` (Telegram branch removed).
- No Redis? `POST /api/v1/searches` falls back to
  `asyncio.create_task(_run_web_search_inline(...))`.
- Real auth shipped (email + password, verification email). The old
  demo `users(id=0)` row may still exist as legacy seed; new code paths
  resolve real `user_id` from the bearer/session.
- Team-scoped searches and team_seen_leads dedupe so members don't
  see each other's already-touched leads.
- `SearchQuery.source` column kept (default `"web"`) for back-compat
  with existing rows; new searches always set `"web"`.

### Decisions the user has confirmed and we should NOT relitigate
- **Auth:** email + password is the chosen flow. Telegram Login Widget
  is still on the table as an additional option, but don't replace
  email auth with it.
- **Queue:** Redis + arq worker is the production path. Inline
  fallback stays as a safety net for local dev.
- **Lead persistence:** web-origin leads are kept forever. Telegram
  leads still deleted after delivery.
- **Pricing UI:** USD-only on plan cards (PR #13). No рубли, no UAH
  display on the public pricing page.
- **Brand:** "Convioo" everywhere user-facing. Python package stays
  `leadgen` for import stability.

### Already built across PRs #27, #28, #29 (current state)
**PR #27 (merged)**:
- Auth recovery: forgot-password / reset-password / forgot-email
  endpoints, anti-oracle 1-hour single-use tokens reusing the
  existing `email_verification_tokens` table via new ``kind`` values
- HttpOnly + SameSite=Lax session cookie via new ``user_sessions``
  table; logout / logout-all / sessions list+revoke / `/auth/me`
- 10-fail account lockout (15 min) + new-device email + email-changed
  alert + password-changed alert, six new transactional templates (RU)
- Per-IP and per-email rate-limit on every auth endpoint
- Settings → Безопасность (sessions list, revoke, recovery email)
- next.config.js rewrites `/api/*` → Railway so the cookie is first-party
- Search quick wins: `limit` (5/10/20/30/50), Latin-language filter
  fix, fuzzy dedup (place_id OR phone OR domain), `DELETE /api/v1/leads/{id}`
  with `?forever=true` (soft-delete + writes to UserSeenLead)

**PR #28 (merged)**:
- Niche taxonomy YAML (~71 entries with ru/uk/en/de + aliases),
  `GET /api/v1/niches`, NicheCombobox component
- Lead tags (lead_tags + lead_tag_assignments), full CRUD + assign,
  filter on /api/v1/leads, chips + inline editor in modal
- `POST /api/v1/leads/bulk-draft` (up to 20 leads, 3-concurrency)
- Smarter SYSTEM_PROMPT_BASE (BANT/MEDDIC/JTBD/ICP/unit-econ)
- Henry knowledge.py refactored to structured FeatureDoc registry
- OpenStreetMap collector (Nominatim+Overpass) parallel-merged with
  Google via existing fuzzy dedup, `OSM_ENABLED` env switch
- Notion export: `UserIntegrationCredential` + Fernet vault (`FERNET_KEY`),
  `integrations/notion.py`, GET/PUT/DELETE `/api/v1/integrations/notion`,
  `POST /api/v1/leads/export-to-notion`, Settings UI + bulk action

**PR #29 (open, may already be merged)**:
- Migration 0026: search_queries.scope/radius_m/center_lat/center_lon
- Curated city catalogue (~120 entries) + `GET /api/v1/cities` +
  RegionCombobox component
- Shared geocoder (`leadgen/utils/geocode.py`) with TTL cache + single-
  flight, `bbox_from_circle` math
- Pipeline geocodes once, passes bbox to both Google + OSM
- Frontend: scope pills (Город/Метро+радиус/Штат/Страна) + radius
  slider (5/10/25/50/100 km)

### Still NOT built (priority order, see section 12)
- **Stripe payment webhooks** and live billing flow (tables, plan
  cards and `/app/billing` UI exist; money doesn't move). P0.
- **Outreach SEND via Gmail/Outlook OAuth** — drafts exist, no delivery.
- **New Telegram bot** — old aiogram code was deleted; build under a
  fresh adapter calling `run_search_with_sinks`.
- **Multi-source collectors part 2**: Yelp Fusion + Foursquare Places
  (OSM is live; these need API keys).
- **Custom statuses + saved segments** (Phase 4 leftovers — replace
  hardcoded new/contacted/replied/won/archived).
- **Full Notion OAuth** (current MVP uses internal integration tokens).
- **Search scheduling / saved searches**.
- **Public API + API keys** (HubSpot/Pipedrive/Make/Zapier).
- **Mobile polish** — `/app/*` pages assume desktop widths.
- **i18n completion** — `lib/i18n.tsx` half-empty.
- **Sentry / structured logging**.
- **Admin/ops dashboard** at `/app/admin`.
- **Per-team rate limits / quota UI**.

### Open Railway tasks (USER must click in Railway UI)
1. After each deploy verify the latest migration landed and the API
   is up: `curl <Railway-URL>/health`.
   `RAILWAY_GIT_COMMIT_SHA` in the response should match the head SHA.
2. **`FERNET_KEY` MUST be set** (PR #28). Generate once with
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   and paste into Railway Variables. Without it, Notion-token decryption
   resets to the dev fallback on every container restart, breaking
   already-saved integrations.
3. (For multi-user scale) provision Redis → set `REDIS_URL` → add a
   second Railway service with start command:
   `arq leadgen.queue.worker.WorkerSettings`. Without this, every
   web search runs inline in the API process.
4. Confirm `RESEND_API_KEY` + `EMAIL_FROM` are set so verification /
   recovery / password-changed emails actually deliver in prod.
5. Confirm `PUBLIC_APP_URL` = `https://convioo.com` (not localhost).
6. Confirm `BOT_TOKEN` env var is REMOVED from worker service (legacy).
7. Optional: `OSM_ENABLED=false` to disable OSM source if Overpass acts up.

---

## 7. Local dev quickstart

```bash
# Backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill DATABASE_URL, GOOGLE_PLACES_API_KEY, ANTHROPIC_API_KEY
alembic upgrade head
python -m leadgen  # starts FastAPI on :8080

# Tests (23 files, run all)
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
  how to verify it deployed (commit SHA shows up in `/health` and
  in the API startup banner).
- He has Vercel MCP integration granted to you. Use
  `mcp__5c6f7315-…__list_deployments` / `get_deployment_build_logs`
  to debug Vercel deploys without asking him for screenshots.
- He does NOT have a Railway MCP integration. For Railway debugging,
  ask him to share logs.

---

## 9. Common gotchas / lessons (sorted by past-pain)

1. **Vercel build fails with ERESOLVE** → `eslint@9` clashes with
   `eslint-config-next@14.x` peer-dep. Pin eslint to `^8.57`.
2. **Search returns weird results (e.g. roofing → university)** →
   `GooglePlacesCollector` had hardcoded `language="ru"` /
   `region_code="RU"`. Now defaults to `en` / unset.
3. **API crashes silently on startup** → settings used to be
   instantiated at module-level. Now `get_settings()` is lazy and
   logs the error if env vars missing.
4. **Postgres has tables but alembic_version is empty** →
   `entrypoint.sh` runs `alembic upgrade head`, falls back to
   `alembic stamp head` if upgrade fails, ALWAYS runs `python -m
   leadgen` so the API at least starts.
5. **JSONB / UUID don't work in SQLite** → `_JSONB` and `_UUID`
   TypeDecorator wrappers in `db/models.py` switch to JSON / CHAR(36)
   on SQLite, native types on Postgres. Lets unit tests run with
   `aiosqlite` instead of needing a Postgres container.
6. **API keys leaking in logs** → `utils/secrets.sanitize()` scrubs
   Google / Anthropic / Telegram tokens from any string. Wrap response
   bodies before logging them.
7. **`PUBLIC_APP_URL` must be set on Railway**, otherwise email
   verification + invite links are minted relative to localhost.
   Default is `http://localhost:3000` for dev convenience.

---

## 10. Where you should look first depending on the task

| Task | Start here |
|---|---|
| Add a new web API endpoint | `adapters/web_api/app.py` + `schemas.py` |
| Change AI prompt | `analysis/ai_analyzer.py` |
| Change Google Places query shape | `collectors/google_places.py` |
| Change progress / delivery format | new sink in `core/services/` + wire it in `adapters/web_api/sinks.py` |
| Add a new DB column | new alembic migration in `alembic/versions/` + update `db/models.py` |
| Add CI step | `.github/workflows/ci.yml` |
| Frontend page | `frontend/app/<route>/page.tsx` + components in `frontend/components/` |
| Rebuild the Telegram bot | new package under `src/leadgen/adapters/telegram_v2/` (or similar). Build sinks, call `run_search_with_sinks`. Do NOT resurrect the deleted aiogram code. |

---

## 11. Last commit

PR #43 (Phase A part 1 — tech-debt cleanup): FastAPI lifespan
migration, Henry prompt strings extracted into
``leadgen.analysis.prompts`` (ai_analyzer 2569 → 2167 lines),
frontend ``lib/api.ts`` split (1892 → 1522, six new modules under
``lib/api/`` re-exported via barrel). A2 (Pydantic v2) and A3 (Sentry
DSN guards) were no-ops — already clean. A4 (full ``app.py`` split)
and A7 (drop ``/users/{user_id}`` legacy paths) deferred to their
own PRs because of size + auth implications respectively.

PRs #32-#39 (May 3) shipped the rest of the P0/P1/P2
backlog the previous session left:
- #32 T1 + T2: Stripe Checkout / Portal / webhook + Gmail OAuth
  send-as-user + 14-day trial. Stage-mode: empty keys → 503.
- #33 T7: Saved CRM segments / smart-views.
- #34 T8: Saved + scheduled searches with in-process scheduler tick
  (60s loop when REDIS_URL is empty).
- #35 T9: Admin dashboard + ``users.is_admin`` flag.
- #36 T4: Yelp Fusion collector. Niche → ``yelp_categories`` mapping
  in YAML.
- #37 T5: Foursquare Places v3 collector. ``fsq_categories`` in YAML.
- #38 T6: Per-search source toggles (UI checkboxes + JSONB column on
  search_queries).
- #39 T13: Sentry integration (backend ``sentry-sdk`` + frontend
  ``@sentry/nextjs``). DSN-gated, zero overhead when unset.

Earlier batch this session: PR #30 (structlog + rate limits + CI
split + affiliate codes + custom statuses + API keys) and PR #31
(pipeline editor, dynamic kanban, webhook subscriptions).

The Telegram bot was removed in PR #22 and is still pending a
rebuild — when that lands, the new adapter should call
``run_search_with_sinks``.

---

## 12. Roadmap — what's left, in priority order

After this session's batch, the entire P0/P1/P2 ladder from the
previous handoff is in main. What remains is split into:
- **P3 distribution / integrations** (T16-T20 from the previous brief)
- **Cross-cutting tech debt** (T21-T24)
- **UX polish that was always nice-to-have** (T10 mobile, T11 i18n,
  T12 onboarding, T14 per-team analytics, T15 public API docs).

Pick a phase, ship it as one PR, merge, repeat.

### Phase 7 — Make it a paid product (P0)
The product UX is mature enough; the gap to revenue is now plumbing.

1. **Stripe live payments.** Webhook handler (`/api/v1/billing/webhook`),
   plan upgrades / downgrades / cancellations, `users.plan` +
   `users.plan_until` columns. Restore `BILLING_ENFORCED=true` once
   tested. Cards on `/app/billing` already exist; only payment intent
   + webhook plumbing missing.
2. **Trial logic.** New users get 14-day trial of their chosen plan
   regardless of payment, then quotas tighten. `users.trial_ends_at`
   field, banner in `/app` when ≤3 days left.
3. **Customer billing portal.** Use Stripe-hosted portal — link from
   Settings → "Manage subscription".

### Phase 8 — Outreach delivery (P0)
Drafts exist (Phase 4 bulk-draft + per-lead modal). Delivery doesn't
— that makes the CRM read-only for outreach, which kills retention.

1. **Gmail OAuth.** Google Cloud project + send scope. Connect from
   Settings → Интеграции → "Google" (mirror the Notion card pattern).
2. **Send-as-user.** New endpoint `POST /api/v1/leads/{id}/send-email`
   that POSTs to `gmail.users.messages.send`. Log entry into
   `LeadActivity` with kind="email_sent".
3. **Inbox watch (basic).** Poll Gmail for replies via `users.messages.list`
   filtered by message-id header, surface as new `LeadActivity` of
   kind="email_replied". Webhook `gmail.users.watch` for v2.
4. **Outlook OAuth** as a follow-up — same pattern via Microsoft Graph.

### Phase 9 — CRM v2: custom statuses + saved segments (P1)
The hardcoded `new/contacted/replied/won/archived` blocks anyone with
a different sales process from making this their CRM.

1. **`lead_statuses` table** per-team (label, color, order, is_default).
   Migration 0027.
2. Replace hardcoded enum in `Lead.lead_status` with FK + cached label.
   Existing rows → seeded with the five legacy statuses per team.
3. **Settings → Команда → Pipeline Editor**: drag-to-reorder + colour
   picker UI.
4. **`lead_segments` table** (filter JSON, per-user or per-team).
   Sidebar in `/app/leads` — "Saved views" section above smart-filters.
5. **Smart-views builder** — UI to compose `status + tag + score-range
   + last-touched + custom-field` then save as a segment.

### Phase 10 — Multi-source v2: Yelp + Foursquare (P1)
OSM is live (Phase 5a). Yelp + Foursquare close the gap on US/UK.

1. **Yelp Fusion** (`shop.io/fusion`). Free 5k/day, US+CA+UK strong.
   Niche → Yelp category mapping in `niches.yaml` (new `yelp_categories`
   field). New `YelpCollector` mirroring the `OsmCollector` shape.
   `YELP_API_KEY` env, `YELP_ENABLED` toggle.
2. **Foursquare Places** (`developer.foursquare.com`). Global, free
   tier 950 calls/day. Same pattern, `FSQ_API_KEY` env.
3. **Per-source budget allocator**. Pipeline currently sets a hard
   `MAX_RESULTS_PER_QUERY` global cap; split it 50% Google / 25% OSM /
   15% Yelp / 10% FSQ when all enabled. Configurable via env.
4. **UI source toggle** on the search form so the user can disable a
   source per search if Yelp is hot-rate-limited that day.

### Phase 11 — Search scheduling + saved searches (P1)
Re-running a query weekly is the single most-requested workflow once
people have any history.

1. **`saved_searches` table**: niche, region, scope, target_languages,
   limit, schedule_cron, last_run_at, owner_user_id.
2. **Cron worker.** Extend the arq worker (`leadgen/queue/worker.py`)
   with a periodic poll that scans `saved_searches.next_run_at <= now()`
   and enqueues a regular search job per row.
3. **UI on /app/sessions**: "Saved" tab with recurrence picker
   (off / weekly / biweekly / monthly), last-run badge, delta-leads
   counter ("12 new since last week").
4. **Email digest** of new hits via the existing email_sender.

### Phase 12 — Mobile + i18n (P2)
Two-sided polish that drives retention. Shipping order: mobile first
because it's a bigger UX rock; i18n second.

1. **Mobile responsive pass** on `/app/*`. Most pages assume desktop
   widths. Specific work:
   - `/app/leads` kanban → swipeable column carousel under 768px
   - `LeadDetailModal` → full-screen sheet on mobile
   - Sidebar → bottom-nav on mobile
   - Search form → vertical stack with sticky launch button
2. **i18n completion.** `lib/i18n.tsx` is half-empty. Pick UA + EN at
   minimum; add a language detector (browser `navigator.language`).
   Henry already speaks RU/UK/EN — extend the system prompts to
   mirror the user's choice.
3. **Better empty states** on `/app`, `/app/leads`, `/app/sessions`
   when user has 0 data. Current placeholders are weak.
4. **Onboarding tour** — one-time tooltip walkthrough on first
   `/app` visit covering: search form → CRM → Settings.

### Phase 13 — Ops: Sentry + admin + per-team rate limits (P2)
Runs flying blind today. Each item is small but compounds.

1. **Sentry SDK** on the Next.js frontend AND the Python backend
   (already declared but not configured). DSN env var; separate
   projects for `convioo-web` and `convioo-api`.
2. **Structured logging via structlog** (already in deps) with JSON
   output to Railway. Replace ad-hoc `logger.info` formatting.
3. **Admin dashboard** at `/app/admin` (gated on `users.is_admin`):
   user count, MRR proxy from Stripe, error rate from Sentry, recent
   searches, Anthropic spend (already tracked in Prometheus).
4. **Per-team rate limits** on `/api/v1/searches` + `/assistant/chat`
   beyond the personal counter. One user could currently DoS the
   Anthropic bill.
5. **Verify CI pipeline** — `.github/workflows/ci.yml`. Last review
   found Postgres-based CI; newer routes added without coverage may
   slip past it.

### Phase 14 — Distribution: public API + Zapier (P3)
Lets people pipe leads into HubSpot / Pipedrive / their own systems
without us building a connector for each.

1. **API key issuance** — `POST /api/v1/api-keys` returns a token,
   stored hashed in `user_api_keys`. Settings → Безопасность → API.
2. **Public REST API** = the existing endpoints, with auth widened
   to accept either session cookie OR `Authorization: Bearer
   <api_key>`. Document via the auto-generated FastAPI docs at
   `/docs`.
3. **Webhook subscriptions** — `webhooks` table (event_type, target_url,
   user_id). Events: `lead.created`, `lead.status_changed`,
   `search.finished`. Outbound POST with HMAC signature.
4. **Zapier app** on top of #2 + #3. Triggers: new lead, search
   finished. Actions: create lead, update status.
5. **Make.com modules** — same surface as Zapier.

### Phase 15 — Notion v2 + more integrations (P3)
Notion MVP shipped (Phase 6) with internal-token flow. Hardens it
+ adds the next two CRMs.

1. **Full Notion OAuth.** Public Notion connector (vs internal
   integration token). Lets users skip the manual "create integration
   + share database" dance.
2. **Two-way Notion sync** — pull status changes from Notion back
   into Convioo via the search cursor.
3. **HubSpot connector** — OAuth + create-contact / update-deal.
4. **Pipedrive connector** — OAuth + create-person / move-deal-stage.

### Phase 16 — Telegram bot v2 (P3)
The old aiogram code was deleted in PR #22. New bot rebuilt under
a fresh adapter, calling `run_search_with_sinks`.

1. Decide first: is it (a) a sign-in mechanism via Telegram Login
   Widget, or (b) a notifications + chat surface for already-
   registered users? Pick (b) — easier integration, doesn't fork the
   auth model from Phase 1.
2. Adapter under `src/leadgen/adapters/telegram_v2/`. Build sinks
   `TelegramProgressSink` + `TelegramDeliverySink`. Reuse all the
   `core/services` plumbing.
3. Notifications-on-events when a saved search (Phase 11) finishes
   or a lead replies (Phase 8 inbox watch).

### Phase 17 — Distribution growth (P3)
After scale, before exit. Affiliate / referral motion.

1. **Affiliate codes** — `affiliate_codes` table, partner UI at
   `/app/affiliate`, revenue share automated against Stripe.
2. **Referral codes** — every user gets a personal code; both sides
   get +1 month on signup.
3. **Public landing pages** for affiliates (`/affiliate/[slug]`).

### Cross-cutting tech-debt (do while touching nearby code)
- `adapters/web_api/app.py` is now ~4500 lines. Split into
  `routes/auth.py`, `routes/leads.py`, `routes/teams.py`,
  `routes/integrations.py`, etc., before it doubles again.
- `analysis/ai_analyzer.py` is ~2700 lines mixing parsers, prompts,
  and Henry hooks. Pull prompts into a `prompts/` package.
- Frontend `lib/api.ts` is ~1300 lines. Split into per-resource
  modules (`api/auth.ts`, `api/leads.ts`, `api/integrations.ts`).
- All path-based `user_id` web endpoints predate cookie auth —
  trust the cookie now and drop `user_id` from URLs (a one-time
  refactor per route, can stage over multiple PRs).


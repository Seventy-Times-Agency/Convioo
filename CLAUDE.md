# Convioo — Handoff for the Next Claude Session

> Read this file first. Don't re-explore the repo from scratch — the
> code below is current as of commit `7afdaee` (PR #20, Excel export)
> and tells you what's here, where it lives, what's done, what's next,
> and what NOT to do.
>
> The product was originally codenamed "Leadgen" and the Python package
> on disk is still `src/leadgen/` — don't rename it, the import path is
> stable. The user-facing brand everywhere (frontend, repo, marketing)
> is **Convioo**.

---

## 1. What this is

A B2B lead-generation + lightweight CRM platform for marketing agencies.
User describes their target ("roofing companies in New York"); the
system pulls matching companies from Google Places, scrapes their
websites and reviews, runs every lead through Claude for a personalized
score + outreach advice, then delivers leads into a CRM with statuses,
notes, tasks, activity timeline, custom fields, outreach drafts, and
Excel/CSV export.

- **Web app (Next.js 14 on Vercel)** — the only delivery surface today. 24 pages,
  real email/password auth, dashboard, search → SSE progress, sessions,
  full CRM (`/app/leads`), templates, billing UI, team invites, profile,
  settings, public pages (pricing/help/changelog/comparison/legal).
- **Backend (Python FastAPI)** — runs on Railway, ~10k LoC,
  21 alembic migrations, 20 pytest files.
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
  `RESEND_API_KEY` (when verification email is enabled).
- Optional: `REDIS_URL` (queue), `WEB_API_KEY` (gates SSE),
  `BILLING_ENFORCED=true` (turn quotas back on),
  `RAILWAY_GIT_COMMIT_SHA` (auto-injected, used in /health).
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
GDPR-export / GDPR-delete.
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
Stats: `GET /api/v1/stats`, `GET /api/v1/team`,
`GET /api/v1/queue/status`.

### Schema — 23 migrations
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
fuzzy dedup.

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

### Still NOT built (priority order, see section 12)
- **Stripe payment webhooks** and live billing flow (tables, plan
  cards and `/app/billing` UI exist; money doesn't move).
- **New Telegram bot** — old aiogram code was deleted; needs to be
  rebuilt as a thin adapter on top of `core/services` and
  `run_search_with_sinks`.
- **Multi-source collectors** (OSM / Foursquare / Yelp / LinkedIn).
  Today only Google Places + website.
- **Outreach SEND** — drafts exist, no delivery (no SMTP/Gmail OAuth
  send path yet, only stubs).
- **Search scheduling / saved searches** — re-run a query weekly.
- **Webhooks / Zapier / API key for external CRMs**.
- **Mobile polish** — many `/app/*` pages assume desktop widths.
- **i18n** — strings file exists (`lib/i18n.tsx`), only partially
  populated; many strings still hardcoded English.
- **Admin/ops dashboard** — no internal view of users/usage/errors.
- **Per-team rate limits / quota UI** beyond the personal counter.

### Open Railway tasks (USER must click in Railway UI)
1. After each deploy verify the latest migration landed and the API
   is up: `curl <Railway-URL>/health`.
   `RAILWAY_GIT_COMMIT_SHA` in the response should match the head SHA.
2. (For multi-user scale) provision Redis → set `REDIS_URL` → add a
   second Railway service with start command:
   `arq leadgen.queue.worker.WorkerSettings`. Without this, every
   web search runs inline in the API process.
3. Configure transactional email provider env vars (Resend/Postmark)
   so verification emails actually send in prod.
4. Remove `BOT_TOKEN` from Railway Variables — no longer used.

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

PR #22 (this branch) — Telegram bot removed. Killed
`src/leadgen/bot/`, `src/leadgen/adapters/telegram/`,
`pipeline/progress.py`, three bot-only tests, `BOT_CONCEPT.md`.
Rewired `__main__.py` to start only FastAPI. Dropped `aiogram` from
`pyproject.toml` and `BOT_TOKEN` from `config.py` + `.env.example`.
Renamed package metadata to `convioo`. The web app + Henry remain
untouched. The bot is being rebuilt from scratch — when that lands,
the new adapter should call `run_search_with_sinks`.

Previous shipping order: #20 Excel export · #19 theme toggle +
keyboard shortcuts + PWA · #18 public pricing/help/changelog/
comparison · #17 GDPR + audit log · #16 CSV import + decision-maker
enrichment · #15 Henry active · #14 CRM maturity · #13 USD pricing ·
#12 outreach templates + visible quota · #11 Henry weekly check-in.

---

## 12. Roadmap — what to do next, in priority order

These are open tracks the user can pick from. They reflect what's
actually missing in the code, not aspirations.

### P0 — turn the product into a paid one
1. **Stripe live payments.** Webhook handler, plan upgrades/downgrades,
   `users.plan` + `users.plan_until` fields, gate features when plan
   expires, restore `BILLING_ENFORCED=true` once tested. Cards on
   `/app/billing` already exist; only payment intent + webhook missing.
2. **Email send for outreach.** `LeadDetailModal` already drafts via
   `draftLeadEmail`. Add: connect Gmail/Outlook OAuth (stubs exist),
   send-as-user, log into `LeadActivity`. Without this the CRM is
   read-only outreach.
3. **Real transactional email provider in prod.** Verification + invite
   emails currently go through stubs in dev — ensure Resend/Postmark
   keys are set on Railway and outbound flows are tested end-to-end.

### P1 — make searches richer and more honest
4. **Multi-source collectors.** Add OSM/Overpass (free, EU-strong),
   Foursquare Places, Yelp Fusion. Merge by phone/website fingerprint.
   Drop dependency on Google Places being the only truth.
5. **Saved + scheduled searches.** "Run this query every Monday and
   email me new hits." Tables exist conceptually; needs cron worker
   slot + UI on `/app/sessions`.
6. **Better dedup across runs.** `UserSeenLead` + `TeamSeenLead`
   already exist; expose "exclude already-contacted" toggle and a
   "freshness" filter on the search form.

### P2 — UX polish that drives retention
7. **Mobile responsive pass.** Most `/app/*` pages break under 768px.
   Audit kanban, lead modal, sidebar.
8. **i18n completion.** `lib/i18n.tsx` is half-empty. Pick UA + EN at
   minimum, finish strings, add language detector.
9. **Better empty states** on `/app`, `/app/leads`, `/app/sessions`
   when user has 0 data — current placeholders are weak.
10. **Onboarding tour** (one-time tooltip walkthrough on first
    `/app` visit).

### P3 — scale + ops
11. **Provision Redis on Railway**, add arq worker as a second service.
    Today, every web search blocks an API worker.
12. **Admin dashboard** at `/app/admin` (gated on `users.is_admin`):
    user count, MRR proxy, error rate, recent searches, Anthropic
    spend. Without this you're flying blind.
13. **Sentry / structured logging.** Currently relying on Railway logs
    + Prometheus counters. Add Sentry for the web app (Next.js +
    Python) so user-facing errors are visible.
14. **Rate-limit per team and per IP** on `/api/v1/searches` and
    `/assistant/chat` — single user can currently DoS the Claude bill.
15. **Run pytest + ruff + frontend type-check in CI** on every PR.
    Status of `.github/workflows/ci.yml` should be verified — last
    review found Postgres-based CI, but newer routes added without
    coverage may slip in.

### P4 — distribution
16. **Public API + API keys** for users who want to pipe leads into
    their own CRM (HubSpot, Pipedrive, Notion). Re-use existing
    endpoints, gate by `Authorization: Bearer <api_key>`.
17. **Zapier / Make integration** built on top of #16.
18. **New Telegram bot** as alt surface (the old aiogram code was
    deleted in PR #22). Build under a fresh adapter package; reuse
    `core/services` and `run_search_with_sinks`. Decide first whether
    it should also be a sign-in mechanism (Telegram Login Widget) or
    only a notification + chat surface for already-registered users.
19. **Affiliate / referral codes** — coupon table, partner UI.

### Tech-debt items worth doing while touching nearby code
- `adapters/web_api/app.py` is 4001 lines. Split into
  `routes/auth.py`, `routes/leads.py`, `routes/teams.py`, etc., before
  it doubles again.
- `analysis/ai_analyzer.py` is 2552 lines mixing parsers, prompts,
  and the Henry hooks. Pull prompts into a `prompts/` package.

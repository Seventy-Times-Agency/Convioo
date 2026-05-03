# Convioo — Prompt for the Next Session

> Copy this entire block into the next Claude Code session as the
> opening message. Read `/home/user/Convioo/CLAUDE.md` first; it's
> already current as of `main` after PRs #32-#39 (May 3 2026) — 36
> alembic migrations, ~340 pytest cases, the entire P0/P1/P2 ladder
> shipped. What follows are the **remaining** P3 + tech-debt items
> with concrete implementation notes for each. Ship one phase per
> PR, push to `main`, repeat.

---

## Ground rules (don't relitigate)

- Push directly to `main`, no long-lived branches.
- Russian conversation, direct answers, no filler.
- Do whatever you can autonomously. Where API keys are needed, build
  the code + 503-safe stub the way Stripe/Gmail/Yelp/FSQ are done —
  user adds keys later in Railway.
- Each PR ends with: `pytest -q` green, `ruff check src tests` clean,
  `cd frontend && npm run build` (or typecheck) passes, push, tell
  user the SHA + how to verify on Vercel/Railway.
- Don't resurrect deleted Telegram aiogram code.

---

## Phase A — Tech-debt cleanup

Status after PR #43 (Phase A part 1):
- A1 (lifespan), A5 (prompts/), A6 (frontend api.ts split) ✅ shipped.
- A2 (Pydantic v2) and A3 (Sentry guards) were already done in code
  before — no-ops.
- A4 (full ``app.py`` split, 7400+ lines) and A7 (drop
  ``/users/{user_id}`` legacy paths) are still pending. They're
  carved out into their own PRs because of size + auth-sensitivity
  respectively.

### A4. Split `adapters/web_api/app.py` (7400+ lines)
Move per-resource routes into a new package
`src/leadgen/adapters/web_api/routes/`:
- `auth.py` (register, login, logout*, sessions, recovery, lockout)
- `users.py` (me, patch, change-email/password, audit, GDPR)
- `teams.py` (CRUD, invites, memberships)
- `searches.py` (POST /searches, list, detail, leads, SSE, export)
- `leads.py` (list, patch, mark, custom-fields, activity, tasks,
  CSV import/export, bulk-draft, send-email, export-to-notion, tags)
- `templates.py`
- `tags.py`
- `segments.py` (lead_segments)
- `saved_searches.py`
- `statuses.py` (lead_statuses)
- `niches.py` + `cities.py` (taxonomies)
- `billing.py` (checkout, portal, webhook)
- `integrations.py` (notion CRUD + gmail OAuth)
- `webhooks.py` (subscriptions CRUD)
- `api_keys.py`
- `affiliate.py`
- `admin.py`
- `stats.py` (`/stats`, `/team`, `/queue/status`, `/health`, `/metrics`)
Each module exposes an `APIRouter`, `app.py` shrinks to a factory that
mounts them. Keep the existing path prefixes. Do this in ONE PR even
if it's diff-heavy — splitting it across PRs creates merge hell.

### A5 (done in PR #43). Prompts package extracted.
``leadgen.analysis.prompts`` holds ``SYSTEM_PROMPT_BASE``,
``_format_user_profile``, ``_build_system_prompt``,
``_build_lead_context``, ``_assistant_personal_system_prompt`` and
``_assistant_team_system_prompt``. ``ai_analyzer.py`` 2569 → 2167
lines. Further extraction (per-method inline prompts in
``parse_name``, ``analyze_lead`` etc) can chip away at the rest in
later PRs to push under ~1k LOC.

### A6 (done in PR #43). Frontend api.ts split started.
New ``frontend/lib/api/_core.ts`` owns ``request`` / ``ApiError``;
``billing.ts``, ``gmail.ts``, ``saved_searches.ts``, ``segments.ts``,
``lead_statuses.ts``, ``admin.ts`` extracted. ``api.ts`` 1892 →
1522 lines, re-exports the new modules so existing
``from '@/lib/api'`` imports keep working. Future PRs continue
extracting auth, leads, teams, templates, tags, integrations, etc.

### A7. Drop path-based `user_id` from legacy routes
Pending its own PR (auth-sensitive: current handlers don't actually
check that the path's ``user_id`` matches the authenticated user).
13 endpoints still use ``/api/v1/users/{user_id}/...``. The fix:
inject ``current_user: User = Depends(get_current_user)``, replace
``user_id`` references with ``current_user.id``, change paths to
``/users/me/...``. Add 308 redirects from the old paths for one
release. Update frontend callers. Add tests confirming a session
A cookie can't read user B's data.

**Verification**: full pytest suite still green, frontend builds,
manual smoke of dashboard + a search + opening a lead modal.

---

## Phase B — Mobile responsive pass (T10, 1 PR)

The whole `/app/*` set assumes ≥1024px. On phones it's broken.

### B1. Sidebar → bottom nav under 768px
- `frontend/components/app/Sidebar.tsx` (or wherever nav lives) →
  add a `MobileNav.tsx` that renders fixed-bottom with 5 icons:
  Dashboard / Search / Leads / Sessions / Settings.
- Use Tailwind `hidden md:block` on Sidebar, `md:hidden` on MobileNav.
- Don't break desktop spacing.

### B2. `/app/leads` kanban → swipeable carousel under 768px
- Detect viewport with a `useMediaQuery` hook.
- Mobile: render columns as horizontally-scrollable snap-scroll
  (`overflow-x-auto snap-x snap-mandatory`) with one column visible
  at a time. Status pills above to jump.
- Filters/search bar collapses into a "Фильтры" button that opens a
  sheet.

### B3. `LeadDetailModal` → full-screen sheet on mobile
- Currently a centered modal with fixed width. On mobile,
  `inset-0`, scroll the body, sticky header with close button, sticky
  footer with primary action.
- Tabs (info / activity / tasks / draft) become horizontally scrollable.

### B4. Search form (`/app/search`) — vertical stack
- Henry chat takes full width.
- Form fields stack: niche → region → scope pills → radius slider →
  source toggles → languages → limit → big sticky bottom button
  "Запустить".
- Keep desktop two-column layout intact.

### B5. Touch targets
- Sweep `<button>` minimums to `min-h-[44px]` per Apple HIG.
- Replace any hover-only affordances with always-visible icons.

**Verification**: open production preview on a real phone (or Chrome
DevTools iPhone 13 Pro). Walk through register → search → leads →
modal → settings.

---

## Phase C — i18n completion (T11, 1 PR)

`frontend/lib/i18n.tsx` is half-empty.

### C1. Audit current strings
- `grep -rn "useT\|t('\|t(\"" frontend/app frontend/components` —
  find every key.
- Compare against `frontend/lib/i18n.tsx` dictionaries for `ru` /
  `uk` / `en`. Any key missing → fill in.

### C2. Sweep hardcoded strings
- Public pages (`landing`, `pricing`, `help`, `changelog`, `legal`)
  are mostly Russian-only. Wrap user-facing strings in `t('...')`,
  add to dictionaries.
- App pages: scan for raw cyrillic outside `t(...)` calls.

### C3. Browser language detector
- In `frontend/lib/i18n.tsx`, on first mount when no preference saved,
  read `navigator.language`, map `ru-*` → `ru`, `uk-*` → `uk`,
  fallback `en`.
- Persist to localStorage and to `users.locale` via PATCH /users/me.

### C4. Henry persona language
- `analysis/henry_core.py` already accepts a locale hint. Make sure
  the assistant chat endpoint forwards `current_user.locale` so Henry
  speaks RU/UK/EN to match.

### C5. Email templates
- `core/services/email_sender.py` — render functions take `locale`
  arg today; ensure every caller forwards it. Add EN versions of
  the six recovery/security templates (UA can come later).

**Verification**: switch language in Settings, refresh, confirm UI +
last received email + Henry reply all switch. New incognito session
respects browser language.

---

## Phase D — Empty states + onboarding tour (T12, ~1 PR)

### D1. Better empty states
- `/app` (no searches yet): hero with "Начните с первого поиска" +
  CTA + 3 tile examples ("Кофейни в Берлине", "Стоматологии Праги",
  ...).
- `/app/leads` (no leads yet): explain CRM, link to /app/search.
- `/app/sessions` (no sessions): same pattern.
- `/app/templates` (no templates): "Создать первый шаблон" + 3 seed
  templates ("Холодное интро", "Follow-up через 3 дня", "Спасибо за
  встречу") that one-click import.

### D2. Onboarding tour
- New `useOnboarding` hook reading `users.onboarding_completed_at`
  (add to `users` if not present — small migration).
- On first `/app` visit: 4-step tooltip walkthrough (search → results
  → CRM → settings) using a lightweight library (`@reactour/tour`
  or roll-your-own with a dimmer + popover). Skippable.
- "Пройти тур заново" button in Settings.

**Verification**: incognito → register → land in /app → tour fires.

---

## Phase E — Per-team analytics (T14, 1 PR)

### E1. New page `/app/team/analytics`
Charts for the team owner / admin role:
- Searches per day (last 30d), bar chart
- Leads per source (Google / OSM / Yelp / FSQ), pie
- Conversion funnel by `lead_statuses`
- Top performers (members ranked by leads marked as won)
- Anthropic spend per member (we already track in Prometheus; expose
  via a new `/api/v1/team/{id}/analytics` endpoint)

### E2. Per-team rate-limit visibility
- Surface current quotas: searches today / month, AI calls today.
- Show progress bars and let owner bump limits per member (write to
  a new `team_member_limits` table, migration 0037).

### E3. Permissions
- Only `owner` or `is_admin` sees this page. Others get 403 from API
  + UI shows "Нет прав".

**Use `recharts` or `chart.js` (already in repo? if not, add recharts
— smaller bundle).**

---

## Phase F — Public API docs page (T15, 0.5 PR)

Endpoints + Bearer auth + webhook signatures already exist.

### F1. `/help/api` page in frontend
Static MDX page covering:
- How to issue a key (Settings → Безопасность → API)
- Bearer header format
- Quickstart cURL: list leads, create search, get search status
- Webhook flow: subscribe, signature header
  (`X-Convioo-Signature: t=...,v1=hmac_sha256_hex`), verification
  code snippet (Node + Python), retry behaviour, auto-disable rule
- Rate limits (per-key sliding window)
- Versioning policy (`/api/v1/...` is stable)

### F2. Auto-generated reference link
- FastAPI already exposes `/docs` (Swagger UI) and `/redoc`. Link
  to them from this page. Make sure they're public-readable in prod
  (no API key required to load the schema).

---

## Phase G — Zapier app skeleton (T16, 1 PR — code only, publishing later)

### G1. New repo or subfolder `integrations/zapier/`
- `package.json` with `zapier-platform-core@15`.
- Auth: API Key (Bearer).
- Triggers:
  - `new_lead` — polls `GET /api/v1/leads?since=...` (or webhook
    when `lead.created` hooks are wired).
  - `search_finished` — polls `GET /api/v1/searches?status=success&since=...`.
- Actions:
  - `create_lead` — `POST /api/v1/leads` (need to ensure this
    endpoint accepts external creates; currently leads are created
    only by the pipeline — add an `origin='external'` path).
  - `update_lead_status` — `PATCH /api/v1/leads/{id}`.
- `npx zapier validate` passes.
- README in repo root pointing to publishing steps (user runs
  `zapier register` + `zapier push`).

### G2. Backend prep
- Add `POST /api/v1/leads` (no auth changes — same Bearer flow).
- Add `lead.created` event to webhook bus (already exists for status
  changes).

---

## Phase H — HubSpot connector (T17, 1 PR)

OAuth + push leads as contacts.

### H1. OAuth flow
- `GET /api/v1/integrations/hubspot/authorize` → redirect to HubSpot
  with `crm.objects.contacts.write` scope.
- `GET /api/v1/integrations/hubspot/callback` → exchange code, store
  in `user_oauth_credentials` (migration 0032 already supports
  multi-provider — add `provider='hubspot'`).
- 503-safe when `HUBSPOT_OAUTH_CLIENT_ID` / `_SECRET` empty.

### H2. Push API
- `POST /api/v1/leads/export-to-hubspot` body `{lead_ids: [...]}`.
- Maps lead → HubSpot contact:
  - `firstname` ← split lead.contact_name
  - `lastname` ← split
  - `email` ← lead.email
  - `phone` ← lead.phone
  - `company` ← lead.business_name
  - `website` ← lead.website
  - `lifecyclestage` ← lead.lead_status (mapped)
  - Custom prop `convioo_score` ← lead.score
- Returns count + any per-lead errors.

### H3. UI
- Settings → Интеграции → HubSpot card (mirror Notion).
- `/app/leads` Bulk → "В HubSpot".

---

## Phase I — Pipedrive connector (T18, 1 PR)

Same shape as HubSpot, different API.

### I1. OAuth + tokens stored same way (`provider='pipedrive'`).

### I2. `POST /api/v1/leads/export-to-pipedrive`
- Maps to Pipedrive `/persons` create + `/deals` create with the
  user-selected pipeline.
- User picks default pipeline + stage in Settings card.

### I3. UI mirrors HubSpot.

---

## Phase J — Full Notion OAuth (T19, 0.5 PR)

Notion MVP uses internal integration tokens (user pastes a token).
Move to public OAuth so onboarding is one click.

### J1. Notion OAuth app registration
- User creates "Public Integration" in Notion settings; gets client
  ID + secret. Wire env vars: `NOTION_OAUTH_CLIENT_ID`,
  `NOTION_OAUTH_CLIENT_SECRET`.

### J2. Endpoints
- `GET /api/v1/integrations/notion/authorize` → Notion OAuth URL.
- `GET /api/v1/integrations/notion/callback` → exchange code, store
  access_token + workspace_id in vault.
- Existing `PUT /api/v1/integrations/notion` (database picker) keeps
  working — now reads token from OAuth row instead of user-pasted.
- Keep the manual-token fallback for self-hosters.

### J3. UI
- Settings → Интеграции → Notion card switches "Connect" button to
  redirect-flow. Database selector loads workspaces from token.

---

## Phase K — Telegram bot v2 (T20, 1-2 PRs)

User wants notifications + chat surface, not auth.

### K1. Adapter package
- `src/leadgen/adapters/telegram_v2/` (do NOT use `bot/` — that name
  is poisoned).
- aiogram 3.x. Webhook mode (not long polling) — set `TELEGRAM_BOT_TOKEN`
  + `TELEGRAM_WEBHOOK_SECRET`. Webhook URL:
  `https://<api-host>/api/v1/telegram/webhook`.
- Builds `TelegramProgressSink` + `TelegramDeliverySink` that publish
  to chat IDs subscribed by users.

### K2. Account linking
- User goes to Settings → Telegram → "Подключить" → bot deep link
  with one-time token.
- `/api/v1/integrations/telegram/link` stores `telegram_chat_id` on
  the user row (migration 0037 if not already).

### K3. Notifications
- Saved-search finished → send summary card with delta count + button
  "Открыть в Convioo".
- New email reply (Phase L below) → inline notification.
- Manual `/search <niche> in <city>` command in chat → enqueues a
  search via `run_search_with_sinks`, streams progress as edited
  message updates.

### K4. Settings page
- Toggle which event types ping Telegram.

---

## Phase L — Outlook OAuth (T3, 0.5 PR)

Mirror Gmail flow against Microsoft Graph.

### L1. OAuth
- `GET /api/v1/integrations/outlook/{authorize,callback}` with scope
  `Mail.Send`. Tokens in vault `provider='outlook'`.
- Envs: `MICROSOFT_OAUTH_CLIENT_ID`, `_SECRET`, `_REDIRECT_URI`.
  503-safe when empty.

### L2. Send-as-user
- `POST /api/v1/leads/{id}/send-email` already exists for Gmail.
  Branch on user's connected provider — if Outlook, POST to
  `https://graph.microsoft.com/v1.0/me/sendMail`.
- LeadActivity entry same shape.

### L3. UI
- Settings → Интеграции → Outlook card.
- LeadDetailModal "Отправить" button auto-detects which provider is
  connected; if both, dropdown.

---

## Phase M — Inbox watch v1 (Gmail polling) (extends T2, 0.5 PR)

Without this, the CRM is write-only for outreach.

### M1. Background poller
- arq periodic task `poll_gmail_replies` (every 5 min when REDIS_URL
  set; in-process tick fallback).
- For each user with Gmail connected: query `users.messages.list?q=`
  with In-Reply-To headers from past 30 days of `LeadActivity` of
  kind `email_sent`.
- Match thread → write `LeadActivity` of kind `email_replied`.
- Bump lead status `new` → `contacted` → `replied` if currently lower.

### M2. UI surfacing
- New badge on `/app/leads` "Replied" filter.
- Toast on dashboard "У X лидов есть новые ответы".

(Outlook inbox watch can be a follow-up — same pattern via Microsoft
Graph mail webhooks.)

---

## How to sequence

Recommended order (each = 1 PR):
1. **Phase A** (tech-debt) — unblocks everything else
2. **Phase B** (mobile) — biggest UX win for end users
3. **Phase C** (i18n) — needed before international launch
4. **Phase L + M** (Outlook + inbox watch) — closes the outreach loop
5. **Phase D** (empty states + tour)
6. **Phase E** (analytics)
7. **Phase F** (API docs)
8. **Phase J** (Notion OAuth) — small, polish
9. **Phase G + H + I** (Zapier + HubSpot + Pipedrive) — distribution
10. **Phase K** (Telegram bot v2) — when everything else feels stable

If user pushes for revenue first, prioritize Phase L+M (outreach
delivery is the missing piece keeping users in HubSpot for sending).

---

## Per-PR checklist

Before push:
- [ ] `pytest -q` green
- [ ] `ruff check src tests` clean
- [ ] `cd frontend && npm run build` passes (or at minimum
  `npm run typecheck`)
- [ ] Manual smoke of the changed flow on `npm run dev` + local API
- [ ] CLAUDE.md updated: bump migration count, add PR entry to
  "Already built" section, remove from "Still NOT built", add any new
  env vars to "Open Railway tasks"
- [ ] Commit message: `feat(<area>): <what> (T<N>)` style
- [ ] After push: `gh pr create --draft` then tell user the SHA + URL

---

## Anti-goals (don't waste cycles on these)

- Don't rebuild the deleted Telegram aiogram code; build fresh under
  `telegram_v2/`.
- Don't add Russian-market integrations (Yandex, 2GIS-as-RU,
  amoCRM, Bitrix, YooKassa, рубли).
- Don't enable `BILLING_ENFORCED` without user explicit go-ahead even
  after Stripe smoke.
- Don't add new dependencies casually — audit weekly downloads /
  maintenance status / bundle size first.
- Don't write planning docs unless asked. Work from this prompt +
  CLAUDE.md.

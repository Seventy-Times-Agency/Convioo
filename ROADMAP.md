# Convioo — Product Roadmap, Feature Map & Build Plan

> **Canonical planning doc.** Future Claude sessions: read `CLAUDE.md` first
> (architecture + current state), then this file (product vision, verified
> feature status, and the 5-wave build plan). `AUDIT_2026-06-26.md` holds the
> deep 15-agent code/business audit.
>
> **Status legend:** ✅ BUILT · 🟡 PARTIAL (plumbing exists, extend/finish) · ⬜ MISSING
> **Effort:** S ≈ 1–2 days · M ≈ 3–6 days · L ≈ 1.5–3 weeks
>
> Statuses below were **verified against the code** (June 2026) with file
> evidence — they reflect reality, not aspiration. When you build something,
> flip its status here and add the file refs.

---

## Vision

Convioo is not a "lead-search tool" but an **AI partner for winning clients**:
describe who you're looking for → the system finds, scores, writes, runs the
conversation, and reports back. The human decides; Henry does the rest.

Build order principle: **(make what exists solid + look premium) → (Henry-agent
+ core daily screens) → (unique smart features) → (growth/scale) → (money +
security)**.

---

## Feature Status Map (verified)

### A. Finding leads
- 🟡 **Autopilot / conveyor** — scheduled recurring search IS built (`SavedSearch` schedule + `core/services/saved_searches.py:dispatch_due` + `app.py:358-411` scheduler loop). Missing: full chain search→score→write→follow-up by rules.
- 🟡 **Find look-alike** — ICP extraction built (`core/services/icp_analyzer.py:29-76`, biases scoring). Missing: "from 2-3 leads → find similar" endpoint.
- 🟡 **Intent triggers** — hiring (`collectors/adzuna.py`), new registrations (`collectors/companies_house.py`). Missing: funding, site/stack change, broader signals + a signals service.
- ⬜ **Self-learning scoring** — `analysis/scoring.py` is stateless; no won/lost feedback loop.
- ✅ **Pluggable parser architecture** — modular collectors with per-source toggles (`pipeline/search.py:551-750`). To do: formalize a registry + per-country coverage metadata so it's explicitly "whole-world" and drop-in.
- 🟡 **Magic import** — CSV import built (`frontend/app/app/import/page.tsx`). Missing: freeform text/URL → AI-structured leads.
- 🟡 **Continuous discovery** — saved searches on schedule. Missing: "new in market" differential alerts independent of manual runs.
- ⬜ **Lead recycling** — archive is permanent (`core/services/lead_archive.py`); no re-activation on new signal.

### B. Email & conversation
- ✅ **Per-lead chat / inbox** — threads + reply + frontend (`routes/inbox.py:79-440`, `app/app/inbox`, `EmailMessage` model). Polish: embed the full thread inside the lead card (today `LeadDetailEmailTab` drafts/sends).
- ⬜ **AI sorts incoming replies** — replies logged (`email_reply_tracker.py`) but no classify/suggest.
- 🟡 **Booking calendar** — only a `calendly_url` link embedded in emails. Missing: slot picker + meeting record on lead.
- ✅ **Email templates** — `OutreachTemplate` + `routes/templates.py`. To add: ready-made niche presets.
- ✅ **Email warmup** — daily ramp 20→200 (`core/services/send_quota.py`).
- 🟡 **Spam pre-flight** — email verification only (valid/risky/invalid). Missing: content spam-score before send.
- ⬜ **Auto-translate per recipient country** — email language is one global locale, not per-lead.
- ⬜ **Personalized micro-site per lead.**
- ⬜ **Personalized voice/video per lead.**
- 🟡 **Unsubscribe + suppression** — suppression list/API/enforcement BUILT (`core/services/suppression.py`, `routes/suppressions.py`). Missing: `List-Unsubscribe` header + unsubscribe link/footer + public unsubscribe page.
- 🟡 **Multi-channel** — Telegram for notifications only. Missing: LinkedIn/WhatsApp outreach + unified thread.
- 🟡 **Open/click/reply tracking** — open (pixel) + reply (cron) BUILT. Missing: click tracking.

### C. Henry (AI assistant)
- 🟡 **Henry as agent** — confirm-before-write framework BUILT (`_helpers.py:683-1038` pending-actions), but only 4 actions: profile_patch, team_description, member_description, launch_search. Extend with more actions + multi-step.
- ⬜ **Henry controls the UI** — only `launch_search`; no filter/status/export/queue-email actions.
- ✅ **Henry memory** — `AssistantMemory` + session summarisation (`_helpers.py:792-840`, `henry_core.py:memory_block`).
- ⬜ **Henry streaming** — responses are returned whole (`analysis/advice.py`).
- ⬜ **Deal copilot** — Henry has no lead-thread context.
- ⬜ **AI call-prep dossier.**
- 🟡 **Deep company/DM dossier** — decision-maker extraction built (`analysis/research.py`, `/leads/{id}/enrich/decision-makers`). Missing: rich company/news/risk analysis + "who first".
- 🟡 **Home feed / daily digest** — weekly check-in on demand (`routes/assistant.py:weekly_checkin`); `daily_digest_enabled` flag unimplemented. Missing: daily digest + a "what to do now" feed UI + automation.

### D. Telegram
- 🟡 **Bot v2** — `/start` linking, `/search`, `/help` (`adapters/telegram_v2/bot.py`). Missing: proactive Henry reports, hot-lead alerts, command control.

### E. Growth / agency / analytics
- 🟡 **Outreach analytics** — reply counts in reports. Missing: per-template open/reply/meeting funnel.
- ⬜ **Pipeline $ forecast.**
- ✅ **White-label** — `ClientReport`, team branding (`routes/teams.py:382-482`), public reports, `BrandingSection`.
- ⬜ **Website-visitor de-anonymization.**
- ⬜ **Benchmark comparison.**
- ⬜ **Job-change radar.**
- ⬜ **Smart send-time.**
- 🟡 **Two-way HubSpot/Pipedrive** — push built; no pull. (Notion two-way is the pattern to copy.)
- ⬜ **Chrome extension.**
- 🟡 **In-app academy** — onboarding quickstart/tour only. Missing: course content.
- 🟡 **Team collaboration** — team model + role perms + `assigned` activity exist; no shared inbox / assignment UI+endpoint.

### F. Foundation / UX / language
- 🟡 **Design system** — tokens + `.btn/.card/.input/.chip` in `globals.css`; but ~900 inline `style={{}}` across components and no skeleton-loader library. Build a `components/ui/*` layer + skeletons, migrate screens.
- 🟡 **Language** — full i18n (en/uk/ru), persists to `users.language_code`, propagates to Henry + emails. Change wanted: move switcher off the landing into settings, and **split UI-language from outreach-language** (today one field drives both).
- 🟡 **Connector reliability** — all on current APIs (Yelp/Foursquare v3), rate-limit handling, SSRF guard. To do: live end-to-end QA per connector + smoke tests; watch v3 sunset.

### G. Money & security
- 🟡 **Plan taxonomy** — **8 distinct plan names** across pricing page / billing page / `tariff_limits.py` / Stripe map → must consolidate to one set.
- ✅ **Billing infra** — Stripe checkout/portal/webhooks; `BILLING_ENFORCED=false`. To do at monetization: turn on, set `queries_limit` from plan on subscription events, fix the hardcoded `queries_limit=100000` on signup (`auth.py:178`).
- ⬜ **Cost cap** — `usage_tracker.get_user_usage` is dead code (no consumer). Wire enforcement + admin view + alert.
- ✅ **GDPR export/erase** — `GET/DELETE /users/me` + cascade. Missing: lead-level erasure + retention TTL.
- 🟡 **CI security scanners** — pip-audit / npm audit / gitleaks present but advisory (`continue-on-error`). Flip to blocking after backlog clears.
- 🟡 **Security hardening** — in-memory rate limiter (single-instance only), reset/verify/invite tokens stored raw in DB (hash them), SSRF guard present. Full pass at the end.

---

## Build Plan — 5 Waves

> Each task: **what · where (files) · how · effort**. "[extend]" = plumbing
> exists, "[new]" = from scratch.

### WAVE 1 — FOUNDATION
*Goal: existing product is solid and looks premium; base for everything else.*
1. **Design-system layer + skeletons** [extend] — `frontend/components/ui/*` from `globals.css` tokens; replace inline styles screen-by-screen; add `Skeleton`, replace native `prompt()` with `Modal`. **L**
2. **Language rework** [extend] — remove `LanguageSwitcher` from `app/page.tsx`; add `ui_language` + `outreach_language` (split) on `User`; wire `outreach_language` into `analysis/email_drafting.py` + sequences; warn on change. **M**
3. **Connector QA** [extend] — smoke tests for every collector/integration; live OAuth pass; `logger.warning` on 401/410 for Yelp/Foursquare. **M**
4. **Finish unsubscribe** [extend] — add `List-Unsubscribe` header + footer + sender postal address in `integrations/gmail.py:build_raw_message` & Outlook; public unsubscribe page → `POST /suppressions`. **M**
5. **Lead-level GDPR** [new] — delete-by-email across tenants + retention TTL cron in `queue/worker.py`. **S–M**
6. **Spam pre-flight** [new] — content spam-score + fixes in the composer (warmup already built). **M**

### WAVE 2 — CORE (daily experience)
*Goal: key screens modern; Henry becomes an agent; conversation hub complete.*
1. **Redesign key screens** [extend] — `app/app/*` on the Wave-1 UI layer + Cmd-K palette. **L**
2. **Extend Henry agent** [extend] — add action types to `_helpers.py` pending-actions (filter, change status, export, queue/draft email); multi-step plans. **L**
3. **Henry controls UI** [extend] — wire new actions to frontend execution; widen `PendingActionKind` (`lib/api/search.ts`). **M**
4. **Henry streaming** [new] — stream tokens from `analysis/advice.py` → `AssistantWidget`. **M**
5. **Per-lead chat polish** [extend] — embed full thread (`/inbox/threads?lead_id=`) into the lead card with composer. **M**
6. **AI reply classification** [new] — classify replies in `cron_email_reply_scan`; route (interested→push, objection→draft, unsubscribe→suppress). **M**
7. **Home feed + daily digest** [extend] — promote `weekly_checkin` to a daily digest + a "what to do now" feed (`routes/feed.py`, dashboard). **M**

### WAVE 3 — SMART (unique engines)
*Goal: what others don't have. Do 3.1 first — others depend on it.*
1. **Formalize parser registry** [extend] — source registry + per-country coverage metadata + planner picks sources by region. **M**
2. **More parsers** [new, iterative] — registries, jobs, directories, reviews, tech-detect. **M+**
3. **Look-alike endpoint** [extend] — from 2-3 lead IDs build a profile → search similar. **M**
4. **Intent signals service** [extend] — `core/services/signals/*` + cron; funding/site/stack/hiring → feed. **L**
5. **Self-learning scoring** [new] — outcome capture → real ICP → bias scoring/targeting. **L**
6. **Deal copilot** [new] — Henry reads lead thread, suggests next step, drafts proposal, executes on confirm. **M**
7. **Multi-channel thread** [new] — generalize `EmailMessage`→`Message(channel)`; LinkedIn/WhatsApp/Telegram (legal-first). **L**
8. **Autopilot conveyor** [extend] — rules engine on top of saved searches: search→score→write→follow-up, with cost guard + human checkpoints. **L**
9. **Magic import** [extend] — freeform text/URL → AI → leads (reuse dedup). **M**
10. **Lead recycling** [new] — re-activate non-responders on new signal. **S**

### WAVE 4 — GROWTH (sell & scale; mostly parallel)
1. **Outreach analytics + pipeline forecast** [extend/new] — funnel per template/sequence; $ forecast. **M**
2. **Telegram proactive reports + alerts + control** [extend] — `adapters/telegram_v2`. **M**
3. **Booking calendar** [new] — slot picker + meeting on lead + reminders. **M**
4. **Team shared inbox + assignment** [extend] — on `routes/inbox.py` + team perms. **M**
5. **Micro-site per lead + voice/video** [new]. **M each**
6. **Call-prep dossier + rich company dossier** [extend] — on `analysis/research.py` + enrichment. **M**
7. **Click tracking** [new] — link rewriting + activity. **S**
8. **Site-visitor de-anon, benchmark, job-change, send-time** [new]. **S–M each**
9. **HubSpot/Pipedrive pull + Chrome extension** [extend/new]. **M + L**
10. **Academy** [new] — `/app/learn` + content. **M**
11. **Auto-translate outreach per country** [new]. **S**

### WAVE 5 — MONEY & SECURITY (last)
1. **Consolidate plan taxonomy** [extend] — one set across pricing/billing/`tariff_limits`/Stripe + test "UI plan → real price + cap". **M** *(needs founder pricing decision)*
2. **Turn on subscription** [extend] — smoke-test Stripe, set `queries_limit` from plan on events, fix signup default. **M**
3. **Cost cap + alerts** [new] — wire `usage_tracker.get_user_usage` → monthly $ ceiling in `pipeline/search.py` + admin leaderboard + Slack/Sentry alert. **M**
4. **Final security hardening** [extend] — flip CI scanners to blocking; Redis-backed rate limiter; hash reset/verify/invite tokens; full authz/IDOR/secret pass. **L** *(after money flows)*

---

## How future sessions should use this file
1. Read `CLAUDE.md` (architecture, stack, gotchas) + this file (product map + plan).
2. Trust the **status legend** — don't rebuild ✅ items; extend 🟡 ones using the cited files.
3. When you ship something, **update its status + file refs here** and in `CLAUDE.md` "current state".
4. Money/security items (Wave 5) need the founder's decisions — don't enable billing or change pricing without sign-off.

# Convioo Zapier App

Zapier integration for [Convioo](https://convioo.com). Lets users wire
their CRM into 6000+ apps without us building a connector for each.

This directory is a self-contained Node project — when you're ready to
submit to the Zapier marketplace, copy it into its own repo
(`convioo-zapier-app/`) and run `zapier register` against it. No
backend code lives here; everything runs against the public REST API.

## What it ships

### Triggers (REST hooks against `/api/v1/webhooks`)

| Trigger | Convioo event |
|---|---|
| **New Lead** | `lead.created` |
| **Lead Status Changed** | `lead.status_changed` |
| **Search Finished** | `search.finished` |

`performSubscribe` POSTs to `/api/v1/webhooks` with the relevant
`event_types` and stores the returned subscription id. `performUnsubscribe`
deletes the subscription when the Zap is turned off. Each trigger
extracts the relevant slice from the webhook envelope built by
`core/services/webhooks.py:_dispatch`.

Convioo signs every delivery two ways:

- `X-Convioo-Signature: sha256=<hmac>` — legacy HMAC over the raw body.
  Kept verbatim for backward compatibility; existing verifiers still work.
- `X-Convioo-Timestamp: <unix_seconds>` plus
  `X-Convioo-Signature-Timestamped: t=<ts>,v1=<hmac>` — a Stripe-style
  signature over `"<ts>.<raw_body>"`. Prefer this one: it lets a receiver
  reject replays by checking freshness. Recompute
  `HMAC-SHA256(secret, f"{t}.{body}")`, compare it constant-time to `v1`,
  and reject the delivery if `abs(now - t) > 300` seconds (5-minute
  tolerance window).

Zapier's incoming hook URL doesn't verify either signature (we don't have
the secret on Zapier's side), but the `delivery_id` is forwarded to
downstream steps so users can dedupe on their side. If you self-host the
receiver, verify the timestamped signature and enforce the tolerance
window above for replay protection.

### Actions

| Action | Endpoint |
|---|---|
| **Create Lead** | `POST /api/v1/searches/import-csv` (one-row import) |
| **Update Lead Status** | `PATCH /api/v1/leads/{lead_id}` |
| **Add Tag to Lead** | `GET /api/v1/leads` then `PUT /api/v1/leads/{lead_id}/tags` |

`Add Tag to Lead` reads existing tags first because the PUT endpoint
**replaces** the entire tag set; otherwise the action would silently
strip tags off the lead. The tag picker is populated from `/api/v1/tags`
via the hidden `tagsList` trigger.

### Auth

Custom auth — user pastes an API key issued at Convioo → Settings →
Безопасность → API. The middleware in `utils/middleware.js` adds it as
`Authorization: Bearer <token>` on every request and surfaces 401/403 as
`RefreshAuthError` so Zapier prompts for a re-auth.

`apiUrl` is exposed as an optional auth field for self-hosted /
staging deployments — defaults to `https://api.convioo.com`.

## Layout

```
zapier-app/
  index.js              ← App definition (auth + triggers + creates)
  authentication.js     ← Custom auth (API key + apiUrl override)
  utils/
    middleware.js       ← Bearer injector + error handler
    restHook.js         ← subscribe / unsubscribe / extract helpers
    samples.js          ← Static sample payloads for the editor
  triggers/
    new_lead.js
    lead_status_changed.js
    search_finished.js
  creates/
    create_lead.js
    update_lead_status.js
    add_lead_tag.js     ← also exports the hidden `tagsList` trigger
  test/triggers.test.js
```

## Local dev

```bash
cd zapier-app
npm install
npm test                 # jest, no network calls
npx zapier validate      # schema check (requires zapier-platform-cli login)
npx zapier test          # run the live integration tests
npx zapier push          # push to your private app version
```

## Submitting to the marketplace

1. Run `npx zapier register "Convioo"` from a fresh clone of the
   extracted repo.
2. Set the production app URL to `https://api.convioo.com`.
3. Add screenshots + descriptions in the Zapier developer dashboard.
4. Run `npx zapier promote 1.0.0` once the app passes review.

For private use (just our team) skip the promote step — invite users
via `npx zapier users:add`.

# Convioo — Make.com App

Make.com (ex-Integromat) integration for Convioo. Mirrors the Zapier app with 3 instant triggers and 3 actions.

## Modules

### Triggers (Instant — webhook-based)

| Module | Event listened | Output |
|--------|---------------|--------|
| Watch New Leads | `lead.created` | Full lead object |
| Watch Lead Status Changed | `lead.status_changed` | Lead + from/to status |
| Watch Search Finished | `search.finished` | Search summary |

### Actions

| Module | API call | Purpose |
|--------|----------|---------|
| Create Lead | `POST /api/v1/searches/import-csv` | Import a single lead from external source |
| Update Lead Status | `PATCH /api/v1/leads/{id}` | Move lead in CRM pipeline |
| Add Tag to Lead | `GET lead + PUT /api/v1/leads/{id}/tags` | Attach a tag preserving existing ones |

### Searches

| Module | API call | Purpose |
|--------|----------|---------|
| List Tags | `GET /api/v1/tags` | Return all workspace tags (use as data source) |

---

## Setup in Make.com Developer Portal

1. Go to **make.com → Apps → Create a new app**
2. Name: `Convioo`, label: `Convioo`
3. Under **Connection**, paste the contents of `connection.json`
4. Under **Modules**, create each module from the corresponding JSON file in `modules/`
5. Set the **Base URL** default to `https://api.convioo.com`

### Authentication

The app uses **API Key** auth. Users generate keys from:

> Convioo → Settings → API keys

Keys look like `convioo_pk_...`. They are passed as `Authorization: Bearer <key>` on every request.

### Webhook mechanics

All three trigger modules register a Convioo webhook on connection and auto-delete it when the Make.com scenario is turned off. Convioo signs every delivery with an HMAC-SHA256 header (`X-Convioo-Signature`); Make.com does not verify signatures natively, but the webhook secret is stored in `webhook.data` for custom validation if needed.

---

## Local development

The Convioo public API used by this app is documented at `/docs` on any running instance. The relevant endpoints are:

- `GET /api/v1/auth/me` — verify API key
- `GET /api/v1/tags` — list tags
- `POST /api/v1/webhooks` — register webhook
- `DELETE /api/v1/webhooks/{id}` — deregister webhook
- `POST /api/v1/searches/import-csv` — import leads
- `PATCH /api/v1/leads/{id}` — update lead
- `GET /api/v1/leads/{id}` — get lead (used internally by add-tag to read current tags)
- `PUT /api/v1/leads/{id}/tags` — replace tag set on lead

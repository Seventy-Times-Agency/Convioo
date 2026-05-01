# Convioo browser extension

One-click "save the page I'm looking at as a lead in my CRM."

## What it does

When you're on any company's website (or a TechCrunch article, or a
LinkedIn page) and you want to add the company to your Convioo CRM:

1. Optionally select the company name on the page.
2. Click the Convioo icon in the toolbar.
3. The popup pre-fills name + website + notes from the page metadata.
4. Tweak the fields, click **Save**.
5. The lead lands in your CRM under a session named
   "Browser saves · YYYY-MM-DD".

No backend changes required — uses the existing
`POST /api/v1/searches/import-csv` endpoint.

## Install (developer mode)

1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable **Developer mode** (toggle, top-right).
3. Click **Load unpacked** → select this `browser-extension/` folder.
4. The Convioo icon appears in your toolbar. Pin it.
5. Right-click the icon → **Options** → enter your API URL + user ID.

## Configure

Two fields, set once via the Options page:

- **API URL** — public URL of your Convioo backend (Railway). No
  trailing slash. Example: `https://convioo-production.up.railway.app`.
- **User ID** — the integer user ID from your Convioo account.
  Find it in `/app/profile` on your Convioo site.

## Files

```
manifest.json   — manifest v3 declaration
popup.html/js   — toolbar popup with the save form
options.html/js — settings page (API URL + user ID)
icon.svg        — toolbar icon
```

## Limitations / known issues

- No auth header today — the import endpoint is open. Once the API
  gets per-user API keys (roadmap section §16), the extension should
  be updated to send `Authorization: Bearer <key>`.
- One-row-per-save means saving 5 pages today creates 5 sessions
  named "Browser saves · YYYY-MM-DD". The CRM dedup catches the
  duplicates, but the sessions list will show entries — bundle them
  client-side later if it becomes noisy.
- Chrome / Edge only (Firefox supports manifest v3 but cookies +
  scripting permissions differ slightly; not tested).

"use client";

import { PublicPageShell } from "@/components/PublicPageShell";

const API_BASE = "https://convioo.com";

export default function DevelopersPage() {
  return (
    <PublicPageShell width={880}>
      <div style={{ marginBottom: 32 }}>
        <h1
          style={{
            fontSize: 36,
            fontWeight: 800,
            letterSpacing: "-0.02em",
            margin: "0 0 10px",
          }}
        >
          Developers
        </h1>
        <div style={{ fontSize: 15, color: "var(--text-muted)" }}>
          Public REST API + outbound webhooks. Authentication is shared
          with the SPA: either the session cookie or a Bearer token
          minted from{" "}
          <a href="/app/settings" style={{ color: "var(--accent)" }}>
            Settings → Безопасность → API
          </a>
          . The auto-generated OpenAPI schema lives at{" "}
          <code style={{ fontFamily: "var(--font-mono)" }}>{API_BASE}/docs</code>
          {" "}— it is the source of truth for every endpoint and payload
          shape.
        </div>
      </div>

      <Section title="Quickstart">
        <p>
          Mint an API key in Settings; copy the{" "}
          <code>convioo_pk_…</code> token (we show it once). Then:
        </p>
        <Code>
{`# List your last 20 leads.
curl -s ${API_BASE}/api/v1/leads?limit=20 \\
  -H "Authorization: Bearer convioo_pk_•••"

# Mint a key programmatically (label optional).
curl -s ${API_BASE}/api/v1/api-keys \\
  -H "Authorization: Bearer convioo_pk_•••" \\
  -H "Content-Type: application/json" \\
  -d '{"label": "Zapier"}'

# Revoke a key.
curl -s -X DELETE ${API_BASE}/api/v1/api-keys/<key-id> \\
  -H "Authorization: Bearer convioo_pk_•••"`}
        </Code>
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
          Bearer tokens never expire until you revoke them. Treat them
          like passwords: server-side only, never in browser code.
        </p>
      </Section>

      <Section title="Auth">
        <p>
          Every public endpoint accepts both auth modes. Bearer wins
          when both are present so a script with a stale cookie still
          authenticates correctly:
        </p>
        <ul style={{ paddingLeft: 20, fontSize: 14, lineHeight: 1.6 }}>
          <li>
            <b>Cookie</b>:{" "}
            <code style={{ fontFamily: "var(--font-mono)" }}>convioo_session</code>
            {" "}set by the browser SPA. HttpOnly + SameSite=Lax.
          </li>
          <li>
            <b>Bearer</b>:{" "}
            <code style={{ fontFamily: "var(--font-mono)" }}>
              Authorization: Bearer convioo_pk_…
            </code>
            . Long-lived per-user token from the Settings → API table.
            Hashed at rest, plaintext shown once.
          </li>
        </ul>
        <p>
          On 401 responses the body is JSON like{" "}
          <code>{`{ "detail": "invalid or revoked API key" }`}</code>.
          Rate-limit responses are 429 with a{" "}
          <code style={{ fontFamily: "var(--font-mono)" }}>Retry-After</code>{" "}
          header.
        </p>
      </Section>

      <Section title="Webhooks: events">
        <p>
          Convioo POSTs JSON to your registered URL when one of the
          following events fires. Register URLs in{" "}
          <a href="/app/settings" style={{ color: "var(--accent)" }}>
            Settings → Webhooks
          </a>{" "}
          and use the in-UI <b>Test webhook</b> button to receive a{" "}
          <code>webhook.test</code> ping with a real signature.
        </p>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: 13.5,
          }}
        >
          <thead>
            <tr>
              <Th>Event</Th>
              <Th>When</Th>
              <Th>Payload shape</Th>
            </tr>
          </thead>
          <tbody>
            <Row
              event="lead.created"
              when="A new lead lands in the CRM (search finished, CSV import, manual create)."
              payload="serialize_lead(lead) — id, name, score, status, query_id, created_at, …"
            />
            <Row
              event="lead.status_changed"
              when="Status field flips on a lead the caller owns."
              payload="serialize_lead(lead) with the new status."
            />
            <Row
              event="search.finished"
              when="A search transitions to status=succeeded or failed."
              payload="serialize_search(query) — id, niche, region, status, leads_count, avg_score, …"
            />
            <Row
              event="webhook.test"
              when='Pressed "Test webhook" in Settings.'
              payload={`{ "message": "ping from convioo", "webhook_id": "…" }`}
            />
          </tbody>
        </table>
      </Section>

      <Section title="Webhooks: signature">
        <p>
          Every delivery includes three identifying headers. Verify
          the signature before acting on the payload:
        </p>
        <ul style={{ paddingLeft: 20, fontSize: 14, lineHeight: 1.6 }}>
          <li>
            <code style={{ fontFamily: "var(--font-mono)" }}>X-Convioo-Event</code>{" "}
            — the event name (eg. <code>lead.created</code>).
          </li>
          <li>
            <code style={{ fontFamily: "var(--font-mono)" }}>X-Convioo-Delivery</code>{" "}
            — UUID of this delivery attempt; safe to use for idempotency.
          </li>
          <li>
            <code style={{ fontFamily: "var(--font-mono)" }}>X-Convioo-Signature</code>{" "}
            — <code>sha256=&lt;hex&gt;</code> of HMAC-SHA256(secret, body).
          </li>
        </ul>
        <Code>
{`# Python (FastAPI / Flask) — verify before parsing JSON.
import hmac, hashlib

def verify(secret: str, raw_body: bytes, header: str) -> bool:
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), expected)`}
        </Code>
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
          We retry once on a non-2xx and treat 5 consecutive failures
          as a dead URL — the row auto-flips to <code>active=false</code>.
          Re-enable it from the Settings UI.
        </p>
      </Section>

      <Section title="Webhooks: example payload">
        <Code>
{`POST https://your-app.com/hooks/convioo
Content-Type: application/json
X-Convioo-Event: lead.created
X-Convioo-Delivery: 7c0e…b2a1
X-Convioo-Signature: sha256=8f1e…c3a4

{
  "id": "8a3a91e2-…",
  "name": "Acme Roofing",
  "score": 87,
  "lead_status": "new",
  "phone_e164": "+12125550123",
  "website": "https://acmeroofing.example",
  "query_id": "1d2…",
  "created_at": "2026-05-03T10:14:22Z"
}`}
        </Code>
      </Section>

      <Section title="API keys reference">
        <p>
          Three endpoints, all gated by your session cookie or an
          existing API key:
        </p>
        <ul style={{ paddingLeft: 20, fontSize: 14, lineHeight: 1.6 }}>
          <li>
            <code style={{ fontFamily: "var(--font-mono)" }}>
              GET /api/v1/api-keys
            </code>{" "}
            — list active and revoked keys.
          </li>
          <li>
            <code style={{ fontFamily: "var(--font-mono)" }}>
              POST /api/v1/api-keys
            </code>{" "}
            — body <code>{`{"label": "..."}`}</code>; response includes
            the plaintext token in <code>token</code>.
          </li>
          <li>
            <code style={{ fontFamily: "var(--font-mono)" }}>
              DELETE /api/v1/api-keys/&lt;id&gt;
            </code>{" "}
            — revoke. Idempotent.
          </li>
        </ul>
      </Section>

      <Section title="OpenAPI schema">
        <p>
          The full surface — including request and response shapes for
          every endpoint — is auto-generated by FastAPI:
        </p>
        <ul style={{ paddingLeft: 20, fontSize: 14, lineHeight: 1.6 }}>
          <li>
            <a
              href={`${API_BASE}/docs`}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--accent)" }}
            >
              Interactive Swagger UI
            </a>{" "}
            (try requests in-browser; pass your bearer in the lock icon).
          </li>
          <li>
            <a
              href={`${API_BASE}/openapi.json`}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--accent)" }}
            >
              openapi.json
            </a>{" "}
            (raw schema — feed into Postman, openapi-generator,
            tRPC, etc.).
          </li>
        </ul>
      </Section>
    </PublicPageShell>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section style={{ marginBottom: 32 }}>
      <h2
        style={{
          fontSize: 22,
          fontWeight: 700,
          letterSpacing: "-0.01em",
          margin: "0 0 12px",
        }}
      >
        {title}
      </h2>
      <div style={{ fontSize: 14.5, lineHeight: 1.65, color: "var(--text)" }}>
        {children}
      </div>
    </section>
  );
}

function Code({ children }: { children: string }) {
  return (
    <pre
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "14px 16px",
        fontFamily: "var(--font-mono)",
        fontSize: 12.5,
        overflowX: "auto",
        margin: "10px 0",
      }}
    >
      {children}
    </pre>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        textAlign: "left",
        padding: "8px 10px",
        borderBottom: "1px solid var(--border)",
        fontSize: 12,
        textTransform: "uppercase",
        letterSpacing: 0.5,
        color: "var(--text-muted)",
        fontWeight: 600,
      }}
    >
      {children}
    </th>
  );
}

function Row({
  event,
  when,
  payload,
}: {
  event: string;
  when: string;
  payload: string;
}) {
  return (
    <tr>
      <td
        style={{
          padding: "10px",
          borderBottom: "1px solid var(--border)",
          verticalAlign: "top",
          fontFamily: "var(--font-mono)",
          fontSize: 12.5,
          whiteSpace: "nowrap",
        }}
      >
        {event}
      </td>
      <td
        style={{
          padding: "10px",
          borderBottom: "1px solid var(--border)",
          verticalAlign: "top",
        }}
      >
        {when}
      </td>
      <td
        style={{
          padding: "10px",
          borderBottom: "1px solid var(--border)",
          verticalAlign: "top",
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          color: "var(--text-muted)",
        }}
      >
        {payload}
      </td>
    </tr>
  );
}

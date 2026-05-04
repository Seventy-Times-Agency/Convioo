import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Developer docs — Convioo",
  description: "Convioo public API: authentication, webhooks, events and payload schemas.",
};

const API_BASE = "https://api.convioo.com";

export default function DevelopersPage() {
  return (
    <main
      style={{
        maxWidth: 820,
        margin: "0 auto",
        padding: "48px 24px 80px",
        fontFamily: "var(--font-sans, Inter, sans-serif)",
        color: "var(--text, #111)",
        lineHeight: 1.6,
      }}
    >
      <div style={{ marginBottom: 40 }}>
        <Link
          href="/"
          style={{
            fontSize: 13,
            color: "var(--text-muted, #888)",
            textDecoration: "none",
          }}
        >
          ← Convioo
        </Link>
        <h1
          style={{
            fontSize: 32,
            fontWeight: 700,
            marginTop: 16,
            marginBottom: 8,
            letterSpacing: "-0.02em",
          }}
        >
          Developer docs
        </h1>
        <p style={{ fontSize: 15, color: "var(--text-muted, #666)", margin: 0 }}>
          Convioo public REST API — authentication, webhooks, events, payload
          schemas. Interactive reference at{" "}
          <ExternalLink href={`${API_BASE}/docs`}>{API_BASE}/docs</ExternalLink>
          .
        </p>
      </div>

      <Section id="auth" title="Authentication">
        <p>
          All API requests require an API key. Issue one in{" "}
          <Link href="/app/settings" style={{ color: "var(--accent, #0070f3)" }}>
            Settings → API-ключи
          </Link>
          , then pass it as a{" "}
          <Code>Authorization: Bearer</Code> header.
        </p>
        <p>
          Session cookies (browser) and Bearer tokens both work. Bearer token
          wins when both are present.
        </p>
        <Pre>{`curl ${API_BASE}/api/v1/searches \\
  -H "Authorization: Bearer convioo_pk_<your-key>"`}</Pre>
        <Note>
          API keys are prefixed <Code>convioo_pk_</Code>. They are shown once on
          creation — store them in a secrets manager immediately.
        </Note>
      </Section>

      <Section id="base-url" title="Base URL">
        <Pre>{API_BASE}</Pre>
        <p>
          All paths in this document are relative to this base. Requests from
          the Convioo web app go through the Next.js <Code>/api/*</Code> rewrite
          proxy — external scripts should always hit the Railway URL directly.
        </p>
      </Section>

      <Section id="quickstart" title="Quickstart">
        <SubSection title="1. Get your searches">
          <Pre>{`curl ${API_BASE}/api/v1/searches \\
  -H "Authorization: Bearer convioo_pk_<key>"

# → { "items": [...], "total": 12 }`}</Pre>
        </SubSection>

        <SubSection title="2. List leads for a search">
          <Pre>{`curl "${API_BASE}/api/v1/searches/<search_id>/leads?limit=20" \\
  -H "Authorization: Bearer convioo_pk_<key>"`}</Pre>
        </SubSection>

        <SubSection title="3. Update a lead's status">
          <Pre>{`curl -X PATCH "${API_BASE}/api/v1/leads/<lead_id>" \\
  -H "Authorization: Bearer convioo_pk_<key>" \\
  -H "Content-Type: application/json" \\
  -d '{"lead_status": "contacted"}'`}</Pre>
        </SubSection>

        <SubSection title="4. Export leads to Notion">
          <Pre>{`curl -X POST "${API_BASE}/api/v1/leads/export-to-notion" \\
  -H "Authorization: Bearer convioo_pk_<key>" \\
  -H "Content-Type: application/json" \\
  -d '{"lead_ids": ["<uuid1>", "<uuid2>"]}'`}</Pre>
        </SubSection>
      </Section>

      <Section id="webhooks" title="Webhooks">
        <p>
          Convioo sends a signed <Code>POST</Code> request to your URL when a
          subscribed event fires. Set up webhooks in{" "}
          <Link
            href="/app/settings/webhooks"
            style={{ color: "var(--accent, #0070f3)" }}
          >
            Settings → Webhooks
          </Link>
          .
        </p>

        <SubSection title="Request headers">
          <table style={tableStyle}>
            <thead>
              <tr>
                <Th>Header</Th>
                <Th>Value</Th>
              </tr>
            </thead>
            <tbody>
              {[
                ["X-Convioo-Signature", "sha256=<HMAC-SHA256 hex digest>"],
                ["X-Convioo-Event", "lead.created | lead.status_changed | search.finished | webhook.test"],
                ["X-Convioo-Delivery", "unique delivery UUID"],
                ["Content-Type", "application/json"],
                ["User-Agent", "Convioo-Webhooks/1.0"],
              ].map(([h, v]) => (
                <tr key={h}>
                  <Td mono>{h}</Td>
                  <Td>{v}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </SubSection>

        <SubSection title="Payload envelope">
          <Pre>{`{
  "event": "lead.created",
  "delivery_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "delivered_at": "2026-05-03T14:22:00Z",
  "data": { ... }
}`}</Pre>
        </SubSection>

        <SubSection title="Verifying the signature">
          <p>
            Compute <Code>HMAC-SHA256(secret, raw_body)</Code> and compare it
            with the hex digest in <Code>X-Convioo-Signature</Code> (after the{" "}
            <Code>sha256=</Code> prefix). Use a constant-time comparison to
            prevent timing attacks.
          </p>
          <Pre language="python">{`# Python
import hashlib, hmac

def verify(secret: str, body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header)`}</Pre>
          <Pre language="javascript">{`// Node.js
const crypto = require("crypto");

function verify(secret, body, header) {
  const expected = "sha256=" + crypto
    .createHmac("sha256", secret)
    .update(body)          // Buffer or string
    .digest("hex");
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(header),
  );
}`}</Pre>
        </SubSection>

        <SubSection title="Retry and failure policy">
          <p>
            Convioo considers any <Code>2xx</Code> response a success. If your
            endpoint returns a non-2xx status or times out (5 s) five times in a
            row the webhook is automatically disabled. Re-enable it from
            Settings; the failure counter resets on the next successful
            delivery.
          </p>
        </SubSection>
      </Section>

      <Section id="events" title="Events &amp; payload schemas">
        <SubSection title="lead.created">
          <p>
            Fires when a new lead is delivered into the CRM (end of a search
            pipeline run).
          </p>
          <Pre>{`{
  "event": "lead.created",
  "data": {
    "id": "<uuid>",
    "name": "Acme Roofing",
    "score": 82,
    "lead_status": "new",
    "phone": "+1-555-0100",
    "website": "https://acmeroofing.com",
    "address": "123 Main St, New York, NY",
    "category": "Roofing",
    "rating": 4.6,
    "reviews": 47,
    "source": "google",
    "created_at": "2026-05-03T14:22:00Z"
  }
}`}</Pre>
        </SubSection>

        <SubSection title="lead.status_changed">
          <p>
            Fires when a lead&apos;s <Code>lead_status</Code> is updated (PATCH
            lead endpoint or bulk action in the CRM).
          </p>
          <Pre>{`{
  "event": "lead.status_changed",
  "data": {
    "id": "<uuid>",
    "name": "Acme Roofing",
    "lead_status": "contacted",
    "previous_status": "new",
    "changed_at": "2026-05-03T15:00:00Z"
  }
}`}</Pre>
        </SubSection>

        <SubSection title="search.finished">
          <p>
            Fires when a search pipeline completes (whether successful or
            failed).
          </p>
          <Pre>{`{
  "event": "search.finished",
  "data": {
    "search_id": "<uuid>",
    "niche": "Roofing companies",
    "region": "New York",
    "leads_found": 23,
    "status": "completed",
    "finished_at": "2026-05-03T14:25:00Z"
  }
}`}</Pre>
        </SubSection>

        <SubSection title="webhook.test">
          <p>
            Fires when you click <em>Тест</em> in Settings. Use it to verify
            your endpoint is reachable and signatures validate correctly.
          </p>
          <Pre>{`{
  "event": "webhook.test",
  "data": {
    "webhook_id": "<uuid>",
    "message": "This is a test delivery from Convioo."
  }
}`}</Pre>
        </SubSection>
      </Section>

      <Section id="rate-limits" title="Rate limits">
        <table style={tableStyle}>
          <thead>
            <tr>
              <Th>Endpoint group</Th>
              <Th>Limit</Th>
            </tr>
          </thead>
          <tbody>
            {[
              ["POST /api/v1/searches", "20 req / 10 min per user"],
              ["POST /api/v1/assistant/chat", "60 req / 10 min per user"],
              ["All other endpoints", "300 req / min per key"],
            ].map(([ep, limit]) => (
              <tr key={ep}>
                <Td mono>{ep}</Td>
                <Td>{limit}</Td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          Exceeding a limit returns <Code>429 Too Many Requests</Code> with a{" "}
          <Code>Retry-After</Code> header (seconds).
        </p>
      </Section>

      <Section id="errors" title="Error format">
        <Pre>{`{
  "detail": "human-readable error message"
}`}</Pre>
        <table style={tableStyle}>
          <thead>
            <tr>
              <Th>Status</Th>
              <Th>Meaning</Th>
            </tr>
          </thead>
          <tbody>
            {[
              ["400", "Invalid request body or business-rule violation"],
              ["401", "Missing or invalid credentials"],
              ["403", "Valid credentials, insufficient permissions"],
              ["404", "Resource not found"],
              ["422", "Pydantic validation error (malformed JSON)"],
              ["429", "Rate limit exceeded"],
              ["503", "Feature not configured on this deployment"],
            ].map(([code, desc]) => (
              <tr key={code}>
                <Td mono>{code}</Td>
                <Td>{desc}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section id="openapi" title="Interactive reference">
        <p>
          The full OpenAPI spec (auto-generated by FastAPI) is available at:
        </p>
        <Pre>{`${API_BASE}/docs       # Swagger UI
${API_BASE}/redoc      # ReDoc
${API_BASE}/openapi.json   # raw JSON`}</Pre>
        <p>
          The spec is always up-to-date with the running backend — it documents
          every request/response schema and lists which endpoints require auth.
        </p>
      </Section>
    </main>
  );
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} style={{ marginBottom: 48 }}>
      <h2
        style={{
          fontSize: 22,
          fontWeight: 700,
          marginBottom: 16,
          paddingBottom: 10,
          borderBottom: "1px solid var(--border, #e5e7eb)",
          letterSpacing: "-0.01em",
        }}
        dangerouslySetInnerHTML={{ __html: title }}
      />
      <div
        style={{
          fontSize: 14.5,
          lineHeight: 1.7,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {children}
      </div>
    </section>
  );
}

function SubSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3
        style={{
          fontSize: 15,
          fontWeight: 600,
          marginBottom: 10,
          color: "var(--text, #111)",
        }}
      >
        {title}
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {children}
      </div>
    </div>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code
      style={{
        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        fontSize: "0.88em",
        background: "var(--surface-2, #f4f4f5)",
        padding: "1px 5px",
        borderRadius: 4,
        color: "var(--accent, #0070f3)",
      }}
    >
      {children}
    </code>
  );
}

function Pre({
  children,
  language,
}: {
  children: string;
  language?: string;
}) {
  return (
    <div style={{ position: "relative" }}>
      {language && (
        <div
          style={{
            position: "absolute",
            top: 8,
            right: 12,
            fontSize: 10,
            color: "var(--text-dim, #aaa)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          {language}
        </div>
      )}
      <pre
        style={{
          background: "var(--surface-2, #f4f4f5)",
          borderRadius: 10,
          padding: "14px 16px",
          overflow: "auto",
          fontSize: 12.5,
          lineHeight: 1.6,
          margin: 0,
          fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
          border: "1px solid var(--border, #e5e7eb)",
          whiteSpace: "pre",
        }}
      >
        {children}
      </pre>
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 13,
        color: "var(--text-muted, #666)",
        lineHeight: 1.5,
        padding: "10px 14px",
        borderLeft: "3px solid var(--accent, #0070f3)",
        background: "var(--accent-soft, #eff6ff)",
        borderRadius: "0 8px 8px 0",
      }}
    >
      {children}
    </div>
  );
}

function ExternalLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      style={{ color: "var(--accent, #0070f3)" }}
    >
      {children}
    </a>
  );
}

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 13.5,
};

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        textAlign: "left",
        padding: "8px 12px",
        background: "var(--surface-2, #f4f4f5)",
        borderBottom: "1px solid var(--border, #e5e7eb)",
        fontWeight: 600,
        fontSize: 12,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        color: "var(--text-muted, #666)",
      }}
    >
      {children}
    </th>
  );
}

function Td({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <td
      style={{
        padding: "8px 12px",
        borderBottom: "1px solid var(--border, #e5e7eb)",
        fontFamily: mono
          ? "var(--font-mono, 'JetBrains Mono', monospace)"
          : undefined,
        fontSize: mono ? 12.5 : undefined,
        verticalAlign: "top",
      }}
    >
      {children}
    </td>
  );
}

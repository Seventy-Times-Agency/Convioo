"use client";

import Link from "next/link";
import { useLocale } from "@/lib/i18n";

const API_BASE = "https://api.convioo.com";

export default function DevelopersPage() {
  const { t } = useLocale();
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
          {t("developers.title")}
        </h1>
        <p style={{ fontSize: 15, color: "var(--text-muted, #666)", margin: 0 }}>
          {t("developers.intro")}{" "}
          <ExternalLink href={`${API_BASE}/docs`}>{API_BASE}/docs</ExternalLink>
          .
        </p>
      </div>

      <Section id="auth" title={t("developers.auth.title")}>
        <p>
          {t("developers.auth.p1Pre")}{" "}
          <Link href="/app/settings" style={{ color: "var(--accent, #0070f3)" }}>
            {t("developers.auth.settingsLink")}
          </Link>
          {t("developers.auth.p1Post")}{" "}
          <Code>Authorization: Bearer</Code>.
        </p>
        <p>{t("developers.auth.p2")}</p>
        <Pre>{`curl ${API_BASE}/api/v1/searches \\
  -H "Authorization: Bearer convioo_pk_<your-key>"`}</Pre>
        <Note>
          {t("developers.auth.notePre")} <Code>convioo_pk_</Code>.{" "}
          {t("developers.auth.notePost")}
        </Note>
      </Section>

      <Section id="base-url" title={t("developers.baseUrl.title")}>
        <Pre>{API_BASE}</Pre>
        <p>
          {t("developers.baseUrl.p1Pre")} <Code>/api/*</Code>{" "}
          {t("developers.baseUrl.p1Post")}
        </p>
      </Section>

      <Section id="quickstart" title={t("developers.quickstart.title")}>
        <SubSection title={t("developers.quickstart.step1")}>
          <Pre>{`curl ${API_BASE}/api/v1/searches \\
  -H "Authorization: Bearer convioo_pk_<key>"

# → { "items": [...], "total": 12 }`}</Pre>
        </SubSection>

        <SubSection title={t("developers.quickstart.step2")}>
          <Pre>{`curl "${API_BASE}/api/v1/searches/<search_id>/leads?limit=20" \\
  -H "Authorization: Bearer convioo_pk_<key>"`}</Pre>
        </SubSection>

        <SubSection title={t("developers.quickstart.step3")}>
          <Pre>{`curl -X PATCH "${API_BASE}/api/v1/leads/<lead_id>" \\
  -H "Authorization: Bearer convioo_pk_<key>" \\
  -H "Content-Type: application/json" \\
  -d '{"lead_status": "contacted"}'`}</Pre>
        </SubSection>

        <SubSection title={t("developers.quickstart.step4")}>
          <Pre>{`curl -X POST "${API_BASE}/api/v1/leads/export-to-notion" \\
  -H "Authorization: Bearer convioo_pk_<key>" \\
  -H "Content-Type: application/json" \\
  -d '{"lead_ids": ["<uuid1>", "<uuid2>"]}'`}</Pre>
        </SubSection>
      </Section>

      <Section id="webhooks" title={t("developers.webhooks.title")}>
        <p>
          {t("developers.webhooks.introPre")} <Code>POST</Code>{" "}
          {t("developers.webhooks.introPost")}{" "}
          <Link
            href="/app/settings/webhooks"
            style={{ color: "var(--accent, #0070f3)" }}
          >
            {t("developers.webhooks.settingsLink")}
          </Link>
          .
        </p>

        <SubSection title={t("developers.webhooks.requestHeaders")}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <Th>{t("developers.col.header")}</Th>
                <Th>{t("developers.col.value")}</Th>
              </tr>
            </thead>
            <tbody>
              {[
                ["X-Convioo-Signature", "sha256=<HMAC-SHA256 hex digest> (legacy, kept for compatibility)"],
                ["X-Convioo-Timestamp", "<unix seconds> — when the delivery was signed"],
                ["X-Convioo-Signature-Timestamped", "t=<ts>,v1=<HMAC-SHA256 of \"<ts>.<body>\">"],
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

        <SubSection title={t("developers.webhooks.payloadEnvelope")}>
          <Pre>{`{
  "event": "lead.created",
  "delivery_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "delivered_at": "2026-05-03T14:22:00Z",
  "data": { ... }
}`}</Pre>
        </SubSection>

        <SubSection title={t("developers.webhooks.verifying")}>
          <p>
            {t("developers.webhooks.verifyP1a")}{" "}
            <Code>HMAC-SHA256(secret, raw_body)</Code>{" "}
            {t("developers.webhooks.verifyP1b")}{" "}
            <Code>X-Convioo-Signature</Code> ({t("developers.webhooks.verifyP1c")}{" "}
            <Code>sha256=</Code> {t("developers.webhooks.verifyP1cEnd")}).{" "}
            {t("developers.webhooks.verifyP1d")}
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

        <SubSection title={t("developers.webhooks.replayTitle")}>
          <p>{t("developers.webhooks.replayBody")}</p>
          <Pre language="python">{`# Python — timestamped (replay-safe) verification
import hashlib, hmac, time

def verify_timestamped(secret: str, body: bytes, ts: str, header: str) -> bool:
    # header looks like: t=<ts>,v1=<hex>
    parts = dict(p.split("=", 1) for p in header.split(","))
    if abs(time.time() - int(ts)) > 300:  # 5-minute tolerance
        return False
    expected = hmac.new(
        secret.encode(), f"{ts}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))`}</Pre>
        </SubSection>

        <SubSection title={t("developers.webhooks.retryPolicy")}>
          <p>
            {t("developers.webhooks.retryPre")} <Code>2xx</Code>{" "}
            {t("developers.webhooks.retryPost")}
          </p>
        </SubSection>
      </Section>

      <Section id="events" title={t("developers.events.title")}>
        <SubSection title="lead.created">
          <p>{t("developers.events.leadCreatedDesc")}</p>
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
            {t("developers.events.statusChangedPre")} <Code>lead_status</Code>{" "}
            {t("developers.events.statusChangedPost")}
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
          <p>{t("developers.events.searchFinishedDesc")}</p>
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
            {t("developers.events.webhookTestPre")}{" "}
            <em>{t("developers.events.webhookTestButton")}</em>{" "}
            {t("developers.events.webhookTestPost")}
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

      <Section id="rate-limits" title={t("developers.rateLimits.title")}>
        <table style={tableStyle}>
          <thead>
            <tr>
              <Th>{t("developers.col.endpointGroup")}</Th>
              <Th>{t("developers.col.limit")}</Th>
            </tr>
          </thead>
          <tbody>
            {[
              ["POST /api/v1/searches", "20 req / 10 min per user"],
              ["POST /api/v1/assistant/chat", "60 req / 10 min per user"],
              [t("developers.rateLimits.allOther"), "300 req / min per key"],
            ].map(([ep, limit]) => (
              <tr key={ep}>
                <Td mono>{ep}</Td>
                <Td>{limit}</Td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          {t("developers.rateLimits.exceedPre")}{" "}
          <Code>429 Too Many Requests</Code> {t("developers.rateLimits.exceedMid")}{" "}
          <Code>Retry-After</Code> {t("developers.rateLimits.exceedPost")}
        </p>
      </Section>

      <Section id="errors" title={t("developers.errors.title")}>
        <Pre>{`{
  "detail": "human-readable error message"
}`}</Pre>
        <table style={tableStyle}>
          <thead>
            <tr>
              <Th>{t("developers.col.status")}</Th>
              <Th>{t("developers.col.meaning")}</Th>
            </tr>
          </thead>
          <tbody>
            {[
              ["400", t("developers.errors.e400")],
              ["401", t("developers.errors.e401")],
              ["403", t("developers.errors.e403")],
              ["404", t("developers.errors.e404")],
              ["422", t("developers.errors.e422")],
              ["429", t("developers.errors.e429")],
              ["503", t("developers.errors.e503")],
            ].map(([code, desc]) => (
              <tr key={code}>
                <Td mono>{code}</Td>
                <Td>{desc}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section id="openapi" title={t("developers.openapi.title")}>
        <p>{t("developers.openapi.p1")}</p>
        <Pre>{`${API_BASE}/docs       # Swagger UI
${API_BASE}/redoc      # ReDoc
${API_BASE}/openapi.json   # raw JSON`}</Pre>
        <p>
          {t("developers.openapi.p2")}
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

"use client";

import type { CSSProperties } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { ConviooMark, ConviooWordmark } from "@/components/ConviooLogo";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { PREVIEW_LEADS } from "@/lib/mockLeads";
import { useLocale } from "@/lib/i18n";

export default function HomePage() {
  const { t } = useLocale();

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg)",
        overflow: "hidden",
        position: "relative",
      }}
    >
      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 50,
          background: "color-mix(in srgb, var(--bg) 85%, transparent)",
          backdropFilter: "blur(14px)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div
          style={{
            maxWidth: 1280,
            margin: "0 auto",
            padding: "16px 32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <ConviooWordmark height={32} fallbackTextSize={15} />
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 18,
              fontSize: 13,
              color: "var(--text-muted)",
            }}
          >
            <Link href="/pricing" style={{ color: "inherit" }}>
              {t("public.nav.pricing")}
            </Link>
            <Link href="/help" style={{ color: "inherit" }}>
              {t("public.nav.help")}
            </Link>
            <Link href="/changelog" style={{ color: "inherit" }}>
              {t("public.nav.changelog")}
            </Link>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <LanguageSwitcher compact />
            <Link href="/login" className="btn btn-ghost btn-sm">
              {t("landing.nav.signIn")}
            </Link>
            <Link href="/register" className="btn btn-sm">
              {t("landing.nav.register")}
            </Link>
          </div>
        </div>
      </div>

      <section style={{ position: "relative", padding: "80px 32px 120px", overflow: "hidden" }}>
        <div className="mesh-bg">
          <div className="blob3" />
        </div>
        <div style={{ maxWidth: 1100, margin: "0 auto", position: "relative", textAlign: "center" }}>
          <div className="eyebrow" style={{ marginBottom: 28 }}>
            <span className="status-dot live" style={{ marginRight: 8 }} />
            {t("landing.hero.eyebrow")}
          </div>
          <h1
            style={{
              fontSize: "clamp(52px, 8vw, 112px)",
              fontWeight: 700,
              letterSpacing: "-0.045em",
              lineHeight: 0.95,
              margin: "0 0 32px",
              textWrap: "balance",
            } as CSSProperties}
          >
            {t("landing.hero.titlePre")}{" "}
            <span
              style={{
                background: "linear-gradient(120deg, var(--accent), #EC4899, #F59E0B)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              {t("landing.hero.titleAccent")}
            </span>
            <br />
            {t("landing.hero.titlePost1")}
            <br />
            {t("landing.hero.titlePost2")}
          </h1>
          <p
            style={{
              fontSize: 19,
              color: "var(--text-muted)",
              maxWidth: 620,
              margin: "0 auto 40px",
              lineHeight: 1.55,
              textWrap: "balance",
            } as CSSProperties}
          >
            {t("landing.hero.subtitle")}
          </p>
        </div>

        <div style={{ maxWidth: 1100, margin: "80px auto 0", position: "relative" }}>
          <LandingPreview />
        </div>
      </section>

      <section style={{ maxWidth: 1100, margin: "0 auto", padding: "20px 32px 100px" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 0,
            border: "1px solid var(--border)",
            borderRadius: 16,
            background: "var(--surface)",
            overflow: "hidden",
          }}
        >
          {[
            { num: "90s", label: t("landing.stats.time") },
            { num: "50", label: t("landing.stats.perQuery") },
            { num: "87%", label: t("landing.stats.accuracy") },
            { num: "12×", label: t("landing.stats.speed") },
          ].map((s, i) => (
            <div
              key={s.label}
              style={{
                padding: "28px 24px",
                borderRight: i < 3 ? "1px solid var(--border)" : "none",
              }}
            >
              <div
                style={{
                  fontSize: 42,
                  fontWeight: 700,
                  letterSpacing: "-0.03em",
                  color: "var(--accent)",
                }}
              >
                {s.num}
              </div>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  color: "var(--text-dim)",
                  marginTop: 4,
                }}
              >
                {s.label}
              </div>
            </div>
          ))}
        </div>
      </section>

      <PainSection />

      <section style={{ maxWidth: 1100, margin: "0 auto", padding: "0 32px 120px" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          {t("landing.how.eyebrow")}
        </div>
        <h2
          style={{
            fontSize: 56,
            fontWeight: 700,
            letterSpacing: "-0.03em",
            lineHeight: 1.02,
            margin: "0 0 64px",
            maxWidth: 780,
          }}
        >
          {t("landing.how.title1")}{" "}
          <span style={{ fontStyle: "italic", fontWeight: 400, color: "var(--text-muted)" }}>
            {t("landing.how.titleItalic")}
          </span>{" "}
          {t("landing.how.title2")}
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
          {[
            { n: "01", t: t("landing.how.01.title"), d: t("landing.how.01.body") },
            { n: "02", t: t("landing.how.02.title"), d: t("landing.how.02.body") },
            { n: "03", t: t("landing.how.03.title"), d: t("landing.how.03.body") },
          ].map((s) => (
            <div key={s.n} className="card" style={{ padding: "28px 24px", position: "relative" }}>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  color: "var(--text-dim)",
                  marginBottom: 20,
                }}
              >
                {s.n}
              </div>
              <div
                style={{
                  fontSize: 20,
                  fontWeight: 600,
                  letterSpacing: "-0.01em",
                  marginBottom: 10,
                }}
              >
                {s.t}
              </div>
              <div style={{ fontSize: 14, lineHeight: 1.55, color: "var(--text-muted)" }}>{s.d}</div>
            </div>
          ))}
        </div>
      </section>

      <UseCasesSection />

      <FaqSection />

      <PricingCtaSection />

      <footer
        style={{
          padding: "30px 32px",
          borderTop: "1px solid var(--border)",
          display: "flex",
          justifyContent: "space-between",
          fontSize: 12.5,
          color: "var(--text-dim)",
        }}
      >
        <div>{t("landing.footer.built")}</div>
        <div style={{ display: "flex", gap: 20 }}>
          <Link href="/privacy" style={{ color: "inherit" }}>
            {t("landing.footer.privacy")}
          </Link>
          <Link href="/terms" style={{ color: "inherit" }}>
            {t("landing.footer.terms")}
          </Link>
          <Link href="/cookies" style={{ color: "inherit" }}>
            {t("legal.nav.cookies")}
          </Link>
          <a href="mailto:support@convioo.com" style={{ color: "inherit" }}>
            {t("landing.footer.contact")}
          </a>
        </div>
      </footer>
    </div>
  );
}

function LogoMark() {
  return <ConviooMark size={26} />;
}

function LandingPreview() {
  const { t } = useLocale();
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 20,
        overflow: "hidden",
        boxShadow: "0 40px 100px -20px rgba(15, 15, 20, 0.18)",
        transform: "perspective(1800px) rotateX(3deg)",
      }}
    >
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid var(--border)",
          background: "var(--surface-2)",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <div style={{ display: "flex", gap: 6 }}>
          <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#FF5F57" }} />
          <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#FEBC2E" }} />
          <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#28C840" }} />
        </div>
        <div
          style={{
            flex: 1,
            textAlign: "center",
            fontSize: 12,
            color: "var(--text-muted)",
            fontFamily: "var(--font-mono)",
          }}
        >
          convioo.app/sessions/roofing-nyc
        </div>
      </div>
      <div
        style={{
          padding: 28,
          display: "grid",
          gridTemplateColumns: "200px 1fr",
          gap: 20,
          minHeight: 420,
        }}
      >
        <div>
          <div className="eyebrow" style={{ marginBottom: 14, fontSize: 9 }}>
            {t("preview.session")}
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Roofing · NYC</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 20 }}>
            {t("preview.analyzed", { n: 48 })}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
            <PreviewStatLine label={t("preview.hot")} count={9} temp="hot" />
            <PreviewStatLine label={t("preview.warm")} count={22} temp="warm" />
            <PreviewStatLine label={t("preview.cold")} count={17} temp="cold" />
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {PREVIEW_LEADS.map((l) => (
            <div
              key={l.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 10,
                padding: "12px 14px",
                display: "grid",
                gridTemplateColumns: "auto 1fr auto auto",
                alignItems: "center",
                gap: 14,
              }}
            >
              <span className={"status-dot " + l.temp} />
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: 13.5,
                    fontWeight: 600,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {l.name}
                </div>
                <div
                  style={{
                    fontSize: 11.5,
                    color: "var(--text-muted)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {l.address}
                </div>
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  color: "var(--text-muted)",
                  fontSize: 12,
                }}
              >
                <Icon name="star" size={12} /> {l.rating}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  fontWeight: 600,
                  color:
                    l.score >= 75
                      ? "var(--hot)"
                      : l.score >= 50
                        ? "var(--warm)"
                        : "var(--cold)",
                }}
              >
                {l.score}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function PreviewStatLine({
  label,
  count,
  temp,
}: {
  label: string;
  count: number;
  temp: "hot" | "warm" | "cold";
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between" }}>
      <span style={{ color: "var(--text-muted)" }}>
        <span className={"status-dot " + temp} style={{ marginRight: 6 }} />
        {label}
      </span>
      <span className="mono">{count}</span>
    </div>
  );
}

// ── Pain + before/after ──────────────────────────────────────────────
function PainSection() {
  const { t } = useLocale();
  const manualPts = [
    t("landing.pain.manual.pt1"),
    t("landing.pain.manual.pt2"),
    t("landing.pain.manual.pt3"),
    t("landing.pain.manual.pt4"),
  ];
  const convPts = [
    t("landing.pain.convioo.pt1"),
    t("landing.pain.convioo.pt2"),
    t("landing.pain.convioo.pt3"),
    t("landing.pain.convioo.pt4"),
  ];

  return (
    <section style={{ maxWidth: 1100, margin: "0 auto", padding: "0 32px 120px" }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("landing.pain.eyebrow")}
      </div>
      <h2
        style={{
          fontSize: 56,
          fontWeight: 700,
          letterSpacing: "-0.03em",
          lineHeight: 1.02,
          margin: "0 0 20px",
          maxWidth: 820,
        }}
      >
        {t("landing.pain.title1")}{" "}
        <span style={{ fontStyle: "italic", fontWeight: 400, color: "var(--text-muted)" }}>
          {t("landing.pain.titleItalic")}
        </span>{" "}
        {t("landing.pain.title2")}
      </h2>
      <p
        style={{
          fontSize: 17,
          color: "var(--text-muted)",
          maxWidth: 760,
          lineHeight: 1.55,
          margin: "0 0 48px",
        }}
      >
        {t("landing.pain.lead")}
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 18,
        }}
      >
        <PainColumn
          tone="muted"
          title={t("landing.pain.manual.title")}
          icon="x"
          points={manualPts}
        />
        <PainColumn
          tone="accent"
          title={t("landing.pain.convioo.title")}
          icon="check"
          points={convPts}
        />
      </div>
    </section>
  );
}

function PainColumn({
  tone,
  title,
  icon,
  points,
}: {
  tone: "muted" | "accent";
  title: string;
  icon: "x" | "check";
  points: string[];
}) {
  const isAccent = tone === "accent";
  return (
    <div
      className="card"
      style={{
        padding: "28px 26px",
        borderColor: isAccent ? "var(--accent)" : "var(--border)",
        background: isAccent
          ? "color-mix(in srgb, var(--accent) 6%, var(--surface))"
          : "var(--surface)",
      }}
    >
      <div
        style={{
          fontSize: 14,
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: isAccent ? "var(--accent)" : "var(--text-dim)",
          marginBottom: 18,
        }}
      >
        {title}
      </div>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
        {points.map((p) => (
          <li key={p} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <span
              style={{
                flexShrink: 0,
                width: 22,
                height: 22,
                borderRadius: "50%",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: isAccent
                  ? "var(--accent)"
                  : "color-mix(in srgb, var(--text-dim) 18%, transparent)",
                color: isAccent ? "white" : "var(--text-muted)",
              }}
            >
              <Icon name={icon} size={12} />
            </span>
            <span style={{ fontSize: 14.5, lineHeight: 1.5, color: "var(--text)" }}>{p}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Use cases (with embedded social proof) ──────────────────────────
function UseCasesSection() {
  const { t } = useLocale();
  const cases = [
    {
      tag: t("landing.useCases.01.tag"),
      title: t("landing.useCases.01.title"),
      body: t("landing.useCases.01.body"),
      quote: t("landing.useCases.01.quote"),
      author: t("landing.useCases.01.author"),
    },
    {
      tag: t("landing.useCases.02.tag"),
      title: t("landing.useCases.02.title"),
      body: t("landing.useCases.02.body"),
      quote: t("landing.useCases.02.quote"),
      author: t("landing.useCases.02.author"),
    },
    {
      tag: t("landing.useCases.03.tag"),
      title: t("landing.useCases.03.title"),
      body: t("landing.useCases.03.body"),
      quote: t("landing.useCases.03.quote"),
      author: t("landing.useCases.03.author"),
    },
  ];

  return (
    <section
      style={{
        padding: "80px 32px 100px",
        borderTop: "1px solid var(--border)",
        background: "var(--surface)",
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          {t("landing.useCases.eyebrow")}
        </div>
        <h2
          style={{
            fontSize: 56,
            fontWeight: 700,
            letterSpacing: "-0.03em",
            lineHeight: 1.02,
            margin: "0 0 56px",
            maxWidth: 780,
          }}
        >
          {t("landing.useCases.title1")}{" "}
          <span style={{ fontStyle: "italic", fontWeight: 400, color: "var(--text-muted)" }}>
            {t("landing.useCases.titleItalic")}
          </span>{" "}
          {t("landing.useCases.title2")}
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(310px, 1fr))", gap: 18 }}>
          {cases.map((c) => (
            <div
              key={c.tag}
              className="card"
              style={{
                padding: "26px 24px",
                background: "var(--bg)",
                display: "flex",
                flexDirection: "column",
                gap: 14,
              }}
            >
              <span
                style={{
                  alignSelf: "flex-start",
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  color: "var(--accent)",
                  background: "var(--accent-soft)",
                  padding: "4px 10px",
                  borderRadius: 999,
                }}
              >
                {c.tag}
              </span>
              <div style={{ fontSize: 19, fontWeight: 600, letterSpacing: "-0.01em", lineHeight: 1.25 }}>
                {c.title}
              </div>
              <div style={{ fontSize: 14, lineHeight: 1.55, color: "var(--text-muted)" }}>
                {c.body}
              </div>
              <div
                style={{
                  marginTop: "auto",
                  paddingTop: 16,
                  borderTop: "1px solid var(--border)",
                  fontSize: 13.5,
                  lineHeight: 1.55,
                  color: "var(--text)",
                  fontStyle: "italic",
                }}
              >
                {c.quote}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-dim)",
                  letterSpacing: "0.02em",
                }}
              >
                {c.author}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── FAQ ──────────────────────────────────────────────────────────────
function FaqSection() {
  const { t } = useLocale();
  const items = [
    { q: t("landing.faq.q1"), a: t("landing.faq.a1") },
    { q: t("landing.faq.q2"), a: t("landing.faq.a2") },
    { q: t("landing.faq.q3"), a: t("landing.faq.a3") },
    { q: t("landing.faq.q4"), a: t("landing.faq.a4") },
    { q: t("landing.faq.q5"), a: t("landing.faq.a5") },
  ];
  return (
    <section style={{ maxWidth: 900, margin: "0 auto", padding: "80px 32px 100px" }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("landing.faq.eyebrow")}
      </div>
      <h2
        style={{
          fontSize: 48,
          fontWeight: 700,
          letterSpacing: "-0.03em",
          lineHeight: 1.05,
          margin: "0 0 40px",
        }}
      >
        {t("landing.faq.title")}
      </h2>
      <div style={{ display: "grid", gap: 6 }}>
        {items.map((item, i) => (
          <details
            key={i}
            style={{
              border: "1px solid var(--border)",
              borderRadius: 12,
              background: "var(--surface)",
              padding: "16px 20px",
            }}
          >
            <summary
              style={{
                cursor: "pointer",
                fontSize: 16,
                fontWeight: 600,
                listStyle: "none",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
              }}
            >
              {item.q}
              <Icon name="chevronDown" size={16} />
            </summary>
            <div
              style={{
                fontSize: 14.5,
                lineHeight: 1.6,
                color: "var(--text-muted)",
                marginTop: 12,
              }}
            >
              {item.a}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

// ── Pricing teaser + final CTA ──────────────────────────────────────
function PricingCtaSection() {
  const { t } = useLocale();
  const plans = [
    {
      key: "free" as const,
      name: t("landing.pricing.free.name"),
      price: t("landing.pricing.free.price"),
      body: t("landing.pricing.free.body"),
      highlight: false,
    },
    {
      key: "pro" as const,
      name: t("landing.pricing.pro.name"),
      price: t("landing.pricing.pro.price"),
      body: t("landing.pricing.pro.body"),
      highlight: true,
    },
    {
      key: "agency" as const,
      name: t("landing.pricing.agency.name"),
      price: t("landing.pricing.agency.price"),
      body: t("landing.pricing.agency.body"),
      highlight: false,
    },
  ];
  return (
    <section
      style={{
        padding: "90px 32px 110px",
        borderTop: "1px solid var(--border)",
        background:
          "linear-gradient(180deg, var(--surface) 0%, var(--bg) 60%)",
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          {t("landing.pricing.eyebrow")}
        </div>
        <h2
          style={{
            fontSize: 56,
            fontWeight: 700,
            letterSpacing: "-0.03em",
            lineHeight: 1.02,
            margin: "0 0 16px",
            maxWidth: 780,
          }}
        >
          {t("landing.pricing.title1")}{" "}
          <span style={{ fontStyle: "italic", fontWeight: 400, color: "var(--text-muted)" }}>
            {t("landing.pricing.titleItalic")}
          </span>
        </h2>
        <p
          style={{
            fontSize: 16,
            color: "var(--text-muted)",
            maxWidth: 620,
            lineHeight: 1.5,
            margin: "0 0 48px",
          }}
        >
          {t("landing.pricing.subtitle")}
        </p>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: 14,
            marginBottom: 56,
          }}
        >
          {plans.map((p) => (
            <div
              key={p.key}
              className="card"
              style={{
                padding: "26px 24px",
                borderColor: p.highlight ? "var(--accent)" : "var(--border)",
                background: p.highlight
                  ? "color-mix(in srgb, var(--accent) 6%, var(--surface))"
                  : "var(--surface)",
                display: "flex",
                flexDirection: "column",
                gap: 10,
              }}
            >
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  color: p.highlight ? "var(--accent)" : "var(--text-dim)",
                }}
              >
                {p.name}
              </div>
              <div
                style={{
                  fontSize: 32,
                  fontWeight: 700,
                  letterSpacing: "-0.02em",
                }}
              >
                {p.price}
              </div>
              <div style={{ fontSize: 13.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
                {p.body}
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginBottom: 56 }}>
          <Link
            href="/pricing"
            style={{ color: "var(--accent)", fontSize: 14, fontWeight: 600 }}
          >
            {t("landing.pricing.viewAll")}
          </Link>
        </div>

        <div
          style={{
            textAlign: "center",
            paddingTop: 24,
            borderTop: "1px solid var(--border)",
          }}
        >
          <h2
            style={{
              fontSize: 56,
              fontWeight: 700,
              letterSpacing: "-0.04em",
              lineHeight: 0.98,
              margin: "20px 0 16px",
            }}
          >
            {t("landing.cta.title1")}
            <br />
            <span style={{ fontStyle: "italic", fontWeight: 400, color: "var(--text-muted)" }}>
              {t("landing.cta.title2")}
            </span>
          </h2>
          <div
            style={{
              fontSize: 13,
              color: "var(--text-dim)",
              marginBottom: 28,
            }}
          >
            {t("landing.cta.trialNote")}
          </div>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <Link href="/register" className="btn btn-lg">
              {t("landing.cta.primary")} <Icon name="arrow" size={16} />
            </Link>
            <Link href="/login" className="btn btn-ghost btn-lg">
              {t("landing.cta.secondary")}
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

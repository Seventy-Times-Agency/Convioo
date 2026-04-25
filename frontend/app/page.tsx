"use client";

import type { CSSProperties } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { ConviooMark } from "@/components/ConviooLogo";
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
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <LogoMark />
            <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em" }}>
              Convioo
            </div>
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

      <section
        style={{
          padding: "80px 32px",
          borderTop: "1px solid var(--border)",
          background: "var(--surface)",
        }}
      >
        <div style={{ maxWidth: 900, margin: "0 auto", textAlign: "center", position: "relative" }}>
          <h2
            style={{
              fontSize: 64,
              fontWeight: 700,
              letterSpacing: "-0.04em",
              lineHeight: 0.98,
              margin: "0 0 24px",
            }}
          >
            {t("landing.cta.title1")}
            <br />
            <span style={{ fontStyle: "italic", fontWeight: 400, color: "var(--text-muted)" }}>
              {t("landing.cta.title2")}
            </span>
          </h2>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 36 }}>
            <Link href="/register" className="btn btn-lg">
              {t("landing.cta.primary")} <Icon name="arrow" size={16} />
            </Link>
            <Link href="/login" className="btn btn-ghost btn-lg">
              {t("landing.cta.secondary")}
            </Link>
          </div>
        </div>
      </section>

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
          <a>{t("landing.footer.privacy")}</a>
          <a>{t("landing.footer.terms")}</a>
          <a>{t("landing.footer.contact")}</a>
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

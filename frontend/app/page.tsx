"use client";

import { useState, type CSSProperties } from "react";
import Link from "next/link";
import { ConviooMark } from "@/components/ConviooLogo";
import { HenryAvatar } from "@/components/HenryAvatar";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { LogoTile } from "@/components/app/connectorLogos";
import { useLocale } from "@/lib/i18n";

/* Marketing landing — Convioo "Aurora" (AI-Native Glow), matching the
   approved design reference. Fully localized (RU/UK/EN) via i18n; real
   links to the public pages. Clean glow: gradient + glass + contained
   glows, no floating ambient "nebula" blobs. Code snippets stay in
   English on purpose (they are code). */

const NAV = [
  { key: "lp.nav.features", href: "#features" },
  { key: "lp.nav.integrations", href: "#integrations" },
  { key: "public.nav.pricing", href: "/pricing" },
  { key: "lp.nav.developers", href: "/developers" },
  { key: "public.nav.help", href: "/help" },
] as const;

const SOURCES = ["Google Places", "Yelp", "OpenStreetMap", "Foursquare"];
const AGENCIES = ["Brightside", "Northbeam", "Hoxton & Co", "Kyiv Media Lab", "Astana Growth"];

const INTEGRATIONS = [
  { id: "gmail", n: "Gmail", g: "lp.int.g.email" }, { id: "outlook", n: "Outlook", g: "lp.int.g.email" },
  { id: "hubspot", n: "HubSpot", g: "lp.int.g.crm" }, { id: "pipedrive", n: "Pipedrive", g: "lp.int.g.crm" },
  { id: "notion", n: "Notion", g: "lp.int.g.workspace" }, { id: "sheets", n: "Google Sheets", g: "lp.int.g.workspace" },
  { id: "slack", n: "Slack", g: "lp.int.g.alerts" }, { id: "zapier", n: "Zapier", g: "lp.int.g.automation" }, { id: "make", n: "Make", g: "lp.int.g.automation" },
];

const FEATURE_UI: Record<string, string> = {
  search: 'query: "roofing companies in New York"\nsources: places ✓  yelp ✓  osm ✓  4sq ✓\nfound: 48 → deduped: 32 → enriched: 32',
  henry: 'henry.score(lead) → 86 / 100\n"4.8★, active ads, no booking form"',
  crm: "NEW 12 → CONTACTED 8 → REPLIED 5\n→ WON 3 · LOST 2",
  outreach: "reply in → classify: INTERESTED\nsuggested answer: ready ✓  spf/dkim: pass",
  api: "POST /v1/exports  → 200 OK\nwebhook: lead.scored → slack #leads",
};

const CHAT_LEADS = [
  { name: "Lakeline Dental Studio", score: "82", signalKey: "lp.henry.lead1" },
  { name: "Austin Smiles Group", score: "78", signalKey: "lp.henry.lead2" },
  { name: "Bluebonnet Dental", score: "74", signalKey: "lp.henry.lead3" },
];

const QUOTES = [
  { key: "lp.quote1", name: "Maya Chen", org: "Brightside Agency · Austin", init: "MC" },
  { key: "lp.quote2", name: "Tom Whitfield", org: "Hoxton & Co · London", init: "TW" },
  { key: "lp.quote3", name: "Daria Kovalenko", org: "Kyiv Media Lab", init: "DK" },
];

const eyebrow: CSSProperties = {
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  marginBottom: 14,
};

export default function HomePage() {
  const { t: tStrict } = useLocale();
  // The landing builds keys dynamically (steps/features/tiers/…); loosen the
  // key type so those lookups typecheck. All keys exist in the dictionaries.
  const t = tStrict as (
    key: string,
    vars?: Record<string, string | number>,
  ) => string;
  const [annual, setAnnual] = useState(false);
  const price = (m: number) => (annual ? Math.round(m * 0.8) : m);

  const STEPS = [
    { n: "1", key: "describe" },
    { n: "2", key: "collect" },
    { n: "3", key: "score" },
    { n: "4", key: "outreach" },
  ];
  const FEATURES = [
    { key: "search", span: 2, hl: false },
    { key: "henry", span: 1, hl: true },
    { key: "crm", span: 1, hl: false },
    { key: "outreach", span: 1, hl: false },
    { key: "api", span: 1, hl: false },
  ];
  const TIERS = [
    { key: "starter", price: 29, popular: false, nfeats: 5 },
    { key: "growth", price: 79, popular: true, nfeats: 5 },
    { key: "agency", price: 199, popular: false, nfeats: 5 },
  ];
  const TRUST = ["gdpr", "unsub", "own", "region"];
  const TRUST_ICON: Record<string, string> = { gdpr: "🛡", unsub: "✉", own: "⬇", region: "🌍" };
  const FAQ = ["sources", "how", "credits", "cancel"];
  const FOOTER = [
    { t: "lp.foot.product", links: [["lp.nav.features", "#features"], ["public.nav.pricing", "/pricing"], ["lp.nav.integrations", "#integrations"], ["public.nav.changelog", "/changelog"]] },
    { t: "lp.foot.company", links: [["lp.foot.about", "#"], ["public.nav.help", "/help"], ["lp.foot.contact", "/help"]] },
    { t: "lp.nav.developers", links: [["lp.foot.apidocs", "/developers"], ["lp.foot.status", "#"]] },
    { t: "lp.foot.legal", links: [["lp.foot.privacy", "/privacy"], ["lp.foot.terms", "/terms"], ["lp.foot.cookies", "/cookies"]] },
  ];

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", overflowX: "hidden" }}>
      {/* Header */}
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 50,
          backdropFilter: "blur(18px)",
          background: "color-mix(in srgb, var(--bg) 72%, transparent)",
          borderBottom: "1px solid var(--glass-bd)",
        }}
      >
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 28px", height: 64, display: "flex", alignItems: "center", gap: 24 }}>
          <Link href="/" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <ConviooMark size={26} />
            <span style={{ fontWeight: 800, fontSize: 17, letterSpacing: "-0.01em" }}>Convioo</span>
          </Link>
          <nav style={{ display: "flex", gap: 2, flex: 1 }} className="landing-nav">
            {NAV.map((l) => (
              <Link key={l.href} href={l.href} style={{ padding: "8px 12px", borderRadius: 8, fontSize: 13.5, color: "var(--text-muted)", fontWeight: 500 }}>
                {t(l.key)}
              </Link>
            ))}
          </nav>
          <LanguageSwitcher compact />
          <Link href="/login" style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text-muted)", padding: "7px 6px" }}>
            {t("landing.nav.signIn")}
          </Link>
          <Link href="/register" className="btn btn-sm">
            {t("lp.hero.startFree")}
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section style={{ position: "relative", borderBottom: "1px solid var(--glass-bd)", overflow: "hidden" }}>
        <div className="mesh-bg" />
        <div style={{ position: "relative", maxWidth: 1200, margin: "0 auto", padding: "96px 28px 88px", textAlign: "center" }}>
          <div className="glass" style={{ display: "inline-flex", alignItems: "center", gap: 9, borderRadius: 999, padding: "6px 15px", fontSize: 12.5, color: "var(--text-muted)", marginBottom: 30 }}>
            <span className="gradient-text" style={{ fontWeight: 800 }}>✦ Henry AI</span>
            {t("lp.hero.badge")}
          </div>
          <h1 style={{ fontSize: "clamp(46px, 6.6vw, 82px)", fontWeight: 800, letterSpacing: "-0.04em", lineHeight: 1.02, margin: "0 0 22px" }}>
            {t("lp.hero.title1")}
            <br />
            <span className="gradient-text">{t("lp.hero.title2")}</span>
          </h1>
          <p style={{ fontSize: 18, lineHeight: 1.6, color: "var(--text-muted)", maxWidth: 600, margin: "0 auto 40px" }}>
            {t("lp.hero.subtitle")}
          </p>

          {/* Signature glowing prompt box */}
          <div style={{ maxWidth: 660, margin: "0 auto 22px", position: "relative" }}>
            <div style={{ position: "absolute", inset: -1.5, borderRadius: 16, background: "var(--gradient3)", opacity: 0.75, filter: "blur(12px)" }} />
            <div style={{ position: "relative", borderRadius: 16, background: "var(--gradient3)", padding: 1.5 }}>
              <div style={{ background: "var(--surface)", borderRadius: 14.5, padding: "9px 9px 9px 20px", display: "flex", alignItems: "center", gap: 12 }}>
                <span className="gradient-text" style={{ fontSize: 16, fontWeight: 800 }}>✦</span>
                <span style={{ flex: 1, textAlign: "left", fontSize: 15.5, color: "var(--text)" }}>{t("lp.hero.prompt")}</span>
                <Link href="/register" className="btn" style={{ borderRadius: 10, padding: "12px 22px" }}>{t("lp.hero.find")}</Link>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, justifyContent: "center", marginBottom: 32, flexWrap: "wrap" }}>
            <Link href="/register" className="btn btn-lg">{t("lp.hero.startFree")}</Link>
            <a href="#henry" className="btn btn-ghost btn-lg">◉ {t("lp.hero.watch")}</a>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14, fontSize: 12.5, color: "var(--text-dim)", flexWrap: "wrap" }}>
            <span>{t("lp.hero.noCard")}</span>
            <span style={{ opacity: 0.4 }}>·</span>
            <span>{t("lp.hero.sources")}</span>
            {SOURCES.map((s) => (
              <span key={s} className="glass" style={{ borderRadius: 999, padding: "4px 12px", color: "var(--text-muted)", fontSize: 11.5 }}>{s}</span>
            ))}
          </div>
        </div>

        {/* Henry presence */}
        <div style={{ position: "absolute", right: "max(24px, calc(50% - 590px))", bottom: 40, display: "flex", alignItems: "flex-end", gap: 11 }} className="landing-orb">
          <div className="glass" style={{ borderRadius: "14px 14px 3px 14px", padding: "11px 15px", fontSize: 12.5, color: "var(--text-muted)", maxWidth: 210 }}>
            <span className="gradient-text" style={{ fontWeight: 800 }}>Henry</span> · {t("lp.hero.orb")}
          </div>
          <HenryAvatar size={46} ring />
        </div>
      </section>

      {/* Social proof */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "30px 28px", display: "flex", alignItems: "center", gap: 34, flexWrap: "wrap", justifyContent: "space-between" }}>
          <div style={{ display: "flex", gap: 28, alignItems: "center", flexWrap: "wrap" }}>
            {AGENCIES.map((a) => (
              <span key={a} style={{ fontSize: 13.5, fontWeight: 700, color: "var(--text-dim)" }}>{a}</span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 32 }}>
            {[["2.4M", "lp.metric.leads"], ["4.9/5", "lp.metric.rating"], ["25+", "lp.metric.integrations"]].map(([v, k]) => (
              <div key={k}>
                <div className="gradient-text" style={{ fontSize: 21, fontWeight: 800 }}>{v}</div>
                <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 2 }}>{t(k)}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 28px" }}>
          <div style={{ textAlign: "center", marginBottom: 48 }}>
            <div className="gradient-text" style={eyebrow}>{t("lp.how.eyebrow")}</div>
            <h2 style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.03em", margin: 0 }}>{t("lp.how.title")}</h2>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 18 }}>
            {STEPS.map((s) => (
              <div key={s.n} className="card card-hover" style={{ padding: "26px 24px" }}>
                <div className="brand-mark" style={{ width: 40, height: 40, borderRadius: 12, fontSize: 15, marginBottom: 18 }}>{s.n}</div>
                <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 8 }}>{t(`lp.step.${s.key}.t`)}</div>
                <div style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--text-muted)" }}>{t(`lp.step.${s.key}.d`)}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Feature bento */}
      <section id="features" style={{ borderBottom: "1px solid var(--glass-bd)", scrollMarginTop: 72 }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 28px" }}>
          <div className="gradient-text" style={eyebrow}>{t("lp.platform.eyebrow")}</div>
          <h2 style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 44px" }}>{t("lp.platform.title")}</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 18 }} className="landing-bento">
            {FEATURES.map((f) => (
              <div key={f.key} className="card" style={{ gridColumn: `span ${f.span}`, position: "relative", overflow: "hidden", border: f.hl ? "1px solid var(--glass-bd2)" : undefined }}>
                {f.hl && <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at top right, var(--soft), transparent 60%)", pointerEvents: "none" }} />}
                <div style={{ position: "relative", fontSize: 17, fontWeight: 800, marginBottom: 8, display: "flex", alignItems: "center", gap: 9 }}>
                  {t(`lp.feat.${f.key}.t`)}
                  {f.hl && <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", color: "#fff", background: "var(--gradient3)", borderRadius: 999, padding: "3px 9px" }}>AI</span>}
                </div>
                <div style={{ position: "relative", fontSize: 13.5, lineHeight: 1.6, color: "var(--text-muted)", marginBottom: 18 }}>{t(`lp.feat.${f.key}.d`)}</div>
                <div style={{ position: "relative", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 12, padding: "13px 15px", fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.7, whiteSpace: "pre-line" }}>{FEATURE_UI[f.key]}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Henry spotlight */}
      <section id="henry" style={{ borderBottom: "1px solid var(--glass-bd)", background: "var(--surface)", scrollMarginTop: 72 }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "84px 28px", display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 52, alignItems: "center" }} className="landing-henry">
          <div>
            <div className="glass" style={{ display: "inline-flex", alignItems: "center", gap: 9, borderRadius: 999, padding: "7px 16px", fontSize: 13, fontWeight: 800, marginBottom: 20 }}>
              <span className="brand-mark" style={{ width: 24, height: 24, borderRadius: "50%", fontSize: 12 }}>H</span>
              <span className="gradient-text">{t("lp.henry.badge")}</span>
            </div>
            <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 16px", lineHeight: 1.12 }}>{t("lp.henry.title")}</h2>
            <p style={{ fontSize: 15.5, lineHeight: 1.65, color: "var(--text-muted)", margin: "0 0 24px" }}>{t("lp.henry.body")}</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {["p1", "p2", "p3"].map((p) => (
                <div key={p} style={{ display: "flex", gap: 12, alignItems: "baseline", fontSize: 14 }}>
                  <span className="gradient-text" style={{ fontWeight: 800 }}>✦</span>
                  {t(`lp.henry.${p}`)}
                </div>
              ))}
            </div>
          </div>
          <div style={{ position: "relative" }}>
            <div style={{ position: "absolute", inset: -1, borderRadius: 22, background: "var(--gradient3)", opacity: 0.4, filter: "blur(16px)" }} />
            <div className="card" style={{ position: "relative", padding: 0, overflow: "hidden", border: "1px solid var(--glass-bd2)" }}>
              <div style={{ padding: "13px 18px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
                <div className="brand-mark" style={{ width: 28, height: 28, borderRadius: "50%", fontSize: 13 }}>H</div>
                <span style={{ fontSize: 13.5, fontWeight: 800 }}>Henry</span>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--hot)" }} />
              </div>
              <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ alignSelf: "flex-end", background: "var(--gradient)", color: "#fff", borderRadius: "14px 14px 3px 14px", padding: "11px 15px", fontSize: 13, maxWidth: "85%", lineHeight: 1.5 }}>{t("lp.henry.chatUser")}</div>
                <div style={{ alignSelf: "flex-start", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "14px 14px 14px 3px", padding: "11px 15px", fontSize: 13, maxWidth: "92%", lineHeight: 1.55 }}>{t("lp.henry.chatBot")}</div>
                {CHAT_LEADS.map((cl) => (
                  <div key={cl.name} style={{ display: "flex", alignItems: "center", gap: 12, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 12, padding: "11px 14px" }}>
                    <span style={{ width: 36, height: 36, flexShrink: 0, borderRadius: 10, background: "var(--gradient3)", color: "#fff", display: "grid", placeItems: "center", fontSize: 12.5, fontWeight: 800 }}>{cl.score}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 700 }}>{cl.name}</div>
                      <div style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{t(cl.signalKey)}</div>
                    </div>
                    <span className="gradient-text" style={{ fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>{t("lp.henry.draft")} →</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Integrations */}
      <section id="integrations" style={{ borderBottom: "1px solid var(--glass-bd)", scrollMarginTop: 72 }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 28px", textAlign: "center" }}>
          <div className="gradient-text" style={eyebrow}>{t("lp.int.eyebrow")}</div>
          <h2 style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 12px" }}>{t("lp.int.title")}</h2>
          <p style={{ fontSize: 14.5, color: "var(--text-muted)", margin: "0 auto 40px", maxWidth: 460 }}>{t("lp.int.body")}</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 14, maxWidth: 1000, margin: "0 auto" }}>
            {INTEGRATIONS.map((it) => (
              <div key={it.n} className="card card-hover" style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 16px" }}>
                <LogoTile id={it.id} size={32} />
                <div style={{ textAlign: "left", minWidth: 0 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 700 }}>{it.n}</div>
                  <div style={{ fontSize: 11, color: "var(--text-dim)" }}>{t(it.g)} · <span className="gradient-text" style={{ fontWeight: 700 }}>{t("lp.int.connect")}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" style={{ borderBottom: "1px solid var(--glass-bd)", background: "var(--surface)", scrollMarginTop: 72 }}>
        <div style={{ maxWidth: 1080, margin: "0 auto", padding: "80px 28px" }}>
          <div style={{ textAlign: "center", marginBottom: 40 }}>
            <div className="gradient-text" style={eyebrow}>{t("lp.pricing.eyebrow")}</div>
            <h2 style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 22px" }}>{t("lp.pricing.title")}</h2>
            <div className="seg" style={{ display: "inline-flex" }}>
              <button className={!annual ? "active" : ""} onClick={() => setAnnual(false)} type="button">{t("lp.pricing.monthly")}</button>
              <button className={annual ? "active" : ""} onClick={() => setAnnual(true)} type="button">{t("lp.pricing.annual")}</button>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 18, alignItems: "stretch" }} className="landing-pricing">
            {TIERS.map((tier) => (
              <div key={tier.key} style={{ position: "relative" }}>
                {tier.popular && <div style={{ position: "absolute", inset: -1.5, borderRadius: 21, background: "var(--gradient3)", opacity: 0.5, filter: "blur(10px)" }} />}
                <div className="card" style={{ position: "relative", padding: "28px 26px", display: "flex", flexDirection: "column", height: "100%", boxSizing: "border-box", border: tier.popular ? "1px solid transparent" : undefined, boxShadow: tier.popular ? "0 0 0 1.5px var(--neon-a)" : undefined }}>
                  {tier.popular && <div style={{ position: "absolute", top: -12, left: "50%", transform: "translateX(-50%)", background: "var(--gradient3)", color: "#fff", fontSize: 10.5, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", borderRadius: 999, padding: "4px 14px", whiteSpace: "nowrap" }}>{t("lp.pricing.popular")}</div>}
                  <div style={{ fontSize: 15.5, fontWeight: 800 }}>{t(`lp.tier.${tier.key}.name`)}</div>
                  <div style={{ fontSize: 12.5, color: "var(--text-dim)", margin: "4px 0 20px" }}>{t(`lp.tier.${tier.key}.for`)}</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginBottom: 22 }}>
                    <span className="gradient-text" style={{ fontSize: 42, fontWeight: 800, letterSpacing: "-0.03em" }}>${price(tier.price)}</span>
                    <span style={{ fontSize: 12.5, color: "var(--text-dim)" }}>/ {t("lp.pricing.perMonth")}</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: 1, marginBottom: 24 }}>
                    {Array.from({ length: tier.nfeats }, (_, i) => (
                      <div key={i} style={{ display: "flex", gap: 10, fontSize: 13, color: "var(--text-muted)", alignItems: "baseline" }}>
                        <span style={{ color: "var(--hot)", fontWeight: 800, fontSize: 11 }}>✓</span>
                        {t(`lp.tier.${tier.key}.f${i + 1}`)}
                      </div>
                    ))}
                  </div>
                  <Link href="/register" className={tier.popular ? "btn" : "btn btn-ghost"} style={{ justifyContent: "center" }}>{t(`lp.tier.${tier.key}.cta`)}</Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 28px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 18 }} className="landing-quotes">
            {QUOTES.map((q) => (
              <div key={q.name} className="card" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <div className="gradient-text" style={{ fontSize: 26, fontWeight: 800, lineHeight: 0.6 }}>“</div>
                <div style={{ fontSize: 14.5, lineHeight: 1.6 }}>{t(q.key)}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: "auto" }}>
                  <div style={{ width: 36, height: 36, borderRadius: "50%", background: "var(--gradient3)", display: "grid", placeItems: "center", color: "#fff", fontSize: 12, fontWeight: 800 }}>{q.init}</div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{q.name}</div>
                    <div style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{q.org}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)", background: "var(--surface)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "52px 28px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 26 }}>
          {TRUST.map((tr) => (
            <div key={tr} style={{ display: "flex", gap: 13 }}>
              <span className="glass" style={{ width: 34, height: 34, flexShrink: 0, borderRadius: 10, display: "grid", placeItems: "center", fontSize: 14 }}>{TRUST_ICON[tr]}</span>
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 800, marginBottom: 4 }}>{t(`lp.trust.${tr}.t`)}</div>
                <div style={{ fontSize: 12.5, lineHeight: 1.55, color: "var(--text-muted)" }}>{t(`lp.trust.${tr}.d`)}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)" }}>
        <div style={{ maxWidth: 820, margin: "0 auto", padding: "80px 28px" }}>
          <div style={{ textAlign: "center", marginBottom: 40 }}>
            <div className="gradient-text" style={eyebrow}>{t("lp.faq.eyebrow")}</div>
            <h2 style={{ fontSize: 32, fontWeight: 800, letterSpacing: "-0.03em", margin: 0 }}>{t("lp.faq.title")}</h2>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {FAQ.map((f) => (
              <details key={f} className="card" style={{ padding: "18px 20px" }}>
                <summary style={{ fontSize: 15, fontWeight: 700, cursor: "pointer", listStyle: "none" }}>{t(`lp.faq.${f}.q`)}</summary>
                <div style={{ fontSize: 13.5, color: "var(--text-muted)", lineHeight: 1.6, marginTop: 10 }}>{t(`lp.faq.${f}.a`)}</div>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)", position: "relative", overflow: "hidden" }}>
        <div className="mesh-bg" />
        <div style={{ position: "relative", maxWidth: 1200, margin: "0 auto", padding: "96px 28px", textAlign: "center" }}>
          <h2 style={{ fontSize: "clamp(34px, 5vw, 56px)", fontWeight: 800, letterSpacing: "-0.04em", margin: "0 0 30px" }}>
            {t("lp.cta.title1")}
            <br />
            <span className="gradient-text">{t("lp.cta.title2")}</span>
          </h2>
          <Link href="/register" className="btn btn-lg" style={{ padding: "15px 36px", fontSize: 15.5 }}>{t("lp.hero.startFree")}</Link>
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 16 }}>{t("lp.cta.sub")}</div>
        </div>
      </section>

      {/* Footer */}
      <footer style={{ background: "var(--surface)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "54px 28px 40px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1.4fr repeat(4, 1fr)", gap: 30, marginBottom: 42 }} className="landing-footer">
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 14 }}>
                <ConviooMark size={24} />
                <span style={{ fontWeight: 800, fontSize: 15.5 }}>Convioo</span>
              </div>
              <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.6, maxWidth: 220 }}>{t("lp.foot.tagline")}</div>
            </div>
            {FOOTER.map((fc) => (
              <div key={fc.t}>
                <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-dim)", marginBottom: 14 }}>{t(fc.t)}</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                  {fc.links.map(([k, href]) => (
                    <Link key={k} href={href} style={{ fontSize: 13, color: "var(--text-muted)" }}>{t(k)}</Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div style={{ borderTop: "1px solid var(--glass-bd)", paddingTop: 20, display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, color: "var(--text-dim)", flexWrap: "wrap", gap: 12 }}>
            <span>© 2026 Convioo. {t("lp.foot.rights")}</span>
            <div style={{ display: "flex", gap: 16 }}>
              <a href="#" style={{ color: "var(--text-dim)" }}>X</a>
              <a href="#" style={{ color: "var(--text-dim)" }}>LinkedIn</a>
              <a href="#" style={{ color: "var(--text-dim)" }}>YouTube</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

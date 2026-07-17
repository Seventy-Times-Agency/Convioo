"use client";

import { useState, type CSSProperties } from "react";
import Link from "next/link";
import { ConviooMark } from "@/components/ConviooLogo";
import { HenryAvatar } from "@/components/HenryAvatar";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

/* Marketing landing — Convioo "Aurora" (AI-Native Glow), matching the
   approved design reference. English-first (hard product rule); the app
   itself stays localized. Clean glow: gradient + glass + contained glows,
   no floating ambient "nebula" blobs. */

const NAV = ["Product", "Features", "Integrations", "Pricing", "Developers"];

const SOURCES = ["Google Places", "Yelp", "OpenStreetMap", "Foursquare"];

const AGENCIES = ["Brightside", "Northbeam", "Hoxton & Co", "Kyiv Media Lab", "Astana Growth"];

const METRICS = [
  { v: "2.4M", l: "leads enriched" },
  { v: "4.9/5", l: "average rating" },
  { v: "25+", l: "native integrations" },
];

const STEPS = [
  { n: "1", t: "Describe", d: "Type who you want in plain language — niche, region, any constraint." },
  { n: "2", t: "Collect", d: "Google Places, Yelp, OpenStreetMap and Foursquare — deduplicated, sites scraped for contacts and signals." },
  { n: "3", t: "Henry scores", d: "Fit, quality and buying signals — graded by AI with reasoning you can read." },
  { n: "4", t: "Outreach & CRM", d: "Kanban pipeline, sequences via Gmail/Outlook, AI-classified replies with suggested answers." },
];

const FEATURES = [
  {
    t: "Multi-source search",
    d: "One query, four data sources — deduplicated, then enriched with contacts scraped from each company's website.",
    ui: 'query: "roofing companies in New York"\nsources: places ✓  yelp ✓  osm ✓  4sq ✓\nfound: 48 → deduped: 32 → enriched: 32',
    span: 2,
    hl: false,
  },
  {
    t: "Henry AI copilot",
    d: "Scores every lead, explains why, drafts outreach and answers questions about your pipeline.",
    ui: "henry.score(lead) → 86 / 100\n\"4.8★, active ads, no booking form\"",
    span: 1,
    hl: true,
  },
  {
    t: "CRM kanban",
    d: "Statuses, tags, tasks and a full activity timeline — without leaving Convioo.",
    ui: "NEW 12 → CONTACTED 8 → REPLIED 5\n→ WON 3 · LOST 2",
    span: 1,
    hl: false,
  },
  {
    t: "Outreach engine",
    d: "Email sequences via Gmail & Outlook, AI reply classification with suggested responses, deliverability tools.",
    ui: "reply in → classify: INTERESTED\nsuggested answer: ready ✓  spf/dkim: pass",
    span: 1,
    hl: false,
  },
  {
    t: "Integrations, exports & API",
    d: "Notion, HubSpot, Pipedrive, Sheets, Slack, Zapier, Make — plus one-click Excel/CSV and a public API with webhooks.",
    ui: "POST /v1/exports  → 200 OK\nwebhook: lead.scored → slack #leads",
    span: 1,
    hl: false,
  },
];

const HENRY_POINTS = [
  "Personalized scoring against your service, not a generic grade",
  "Drafts intros in your tone — ready to send or edit",
  "Classifies replies: interested / later / not a fit — with suggested answers",
];

const CHAT_LEADS = [
  { name: "Lakeline Dental Studio", score: "82", signal: "No SSL · site last updated 2019" },
  { name: "Austin Smiles Group", score: "78", signal: "Fails mobile speed check" },
  { name: "Bluebonnet Dental", score: "74", signal: "No online booking form" },
];

const INTEGRATIONS = [
  { n: "Gmail", g: "Email" }, { n: "Outlook", g: "Email" },
  { n: "HubSpot", g: "CRM" }, { n: "Pipedrive", g: "CRM" },
  { n: "Notion", g: "Workspace" }, { n: "Google Sheets", g: "Workspace" },
  { n: "Slack", g: "Alerts" }, { n: "Zapier", g: "Automation" }, { n: "Make", g: "Automation" },
];

const TIERS = [
  { name: "Starter", for: "For solo freelancers", price: 29, popular: false, cta: "Start free", feats: ["300 leads / month", "1 seat", "AI scoring by Henry", "CSV & Excel export", "Email support"] },
  { name: "Growth", for: "For small agencies", price: 79, popular: true, cta: "Start free trial", feats: ["2,000 leads / month", "5 seats", "Sequences + AI reply handling", "All integrations", "Priority support"] },
  { name: "Agency", for: "For teams at scale", price: 199, popular: false, cta: "Talk to sales", feats: ["10,000 leads / month", "Unlimited seats", "API & webhooks", "White-label reports", "Dedicated manager"] },
];

const QUOTES = [
  { text: "Convioo replaced three tools for us. I type a sentence on Monday morning and the pipeline is full by lunch.", name: "Maya Chen", org: "Brightside Agency · Austin", init: "MC" },
  { text: "Henry's scoring is scary good. Our reply rate doubled because we only contact leads worth contacting.", name: "Tom Whitfield", org: "Hoxton & Co · London", init: "TW" },
  { text: "We onboarded the whole team in one afternoon. It just feels finished — rare for tools in this space.", name: "Daria Kovalenko", org: "Kyiv Media Lab", init: "DK" },
];

const TRUST = [
  { icon: "🛡", t: "GDPR-ready", d: "Data processing agreements and EU data residency on request." },
  { icon: "✉", t: "One-click unsubscribe", d: "Every sequence ships with compliant opt-out handling built in." },
  { icon: "⬇", t: "You own your data", d: "Export or delete everything — leads, notes, timelines — any time." },
  { icon: "🌍", t: "EU · UK · US", d: "Built for agencies on both sides of the Atlantic." },
];

const FOOTER_COLS = [
  { t: "Product", links: ["Features", "Pricing", "Integrations", "Changelog"] },
  { t: "Company", links: ["About", "Customers", "Careers", "Contact"] },
  { t: "Developers", links: ["API docs", "Webhooks", "Zapier app", "Status"] },
  { t: "Legal", links: ["Privacy", "Terms", "Cookies", "GDPR"] },
];

const eyebrow: CSSProperties = {
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  marginBottom: 14,
};

export default function HomePage() {
  const [annual, setAnnual] = useState(false);
  const price = (m: number) => (annual ? Math.round(m * 0.8) : m);

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
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <ConviooMark size={26} />
            <span style={{ fontWeight: 800, fontSize: 17, letterSpacing: "-0.01em" }}>Convioo</span>
          </div>
          <nav style={{ display: "flex", gap: 2, flex: 1 }} className="landing-nav">
            {NAV.map((l) => (
              <a key={l} href="#" style={{ padding: "8px 12px", borderRadius: 8, fontSize: 13.5, color: "var(--text-muted)", fontWeight: 500 }}>
                {l}
              </a>
            ))}
          </nav>
          <LanguageSwitcher compact />
          <Link href="/login" style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text-muted)", padding: "7px 6px" }}>
            Log in
          </Link>
          <Link href="/register" className="btn btn-sm">
            Start free
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section style={{ position: "relative", borderBottom: "1px solid var(--glass-bd)", overflow: "hidden" }}>
        <div className="mesh-bg" />
        <div style={{ position: "relative", maxWidth: 1200, margin: "0 auto", padding: "96px 28px 88px", textAlign: "center" }}>
          <div
            className="glass"
            style={{ display: "inline-flex", alignItems: "center", gap: 9, borderRadius: 999, padding: "6px 15px", fontSize: 12.5, color: "var(--text-muted)", marginBottom: 30 }}
          >
            <span className="gradient-text" style={{ fontWeight: 800 }}>✦ Henry AI</span>
            now classifies replies automatically
          </div>
          <h1 style={{ fontSize: "clamp(46px, 6.6vw, 82px)", fontWeight: 800, letterSpacing: "-0.04em", lineHeight: 1.02, margin: "0 0 22px" }}>
            Describe it.
            <br />
            <span className="gradient-text">It&apos;s done.</span>
          </h1>
          <p style={{ fontSize: 18, lineHeight: 1.6, color: "var(--text-muted)", maxWidth: 600, margin: "0 auto 40px" }}>
            One plain-language sentence becomes a scored, enriched, outreach-ready pipeline. Four data sources, one AI analyst, about 90 seconds.
          </p>

          {/* Signature glowing prompt box */}
          <div style={{ maxWidth: 660, margin: "0 auto 22px", position: "relative" }}>
            <div style={{ position: "absolute", inset: -1.5, borderRadius: 16, background: "var(--gradient3)", opacity: 0.75, filter: "blur(12px)" }} />
            <div style={{ position: "relative", borderRadius: 16, background: "var(--gradient3)", padding: 1.5 }}>
              <div style={{ background: "var(--surface)", borderRadius: 14.5, padding: "9px 9px 9px 20px", display: "flex", alignItems: "center", gap: 12 }}>
                <span className="gradient-text" style={{ fontSize: 16, fontWeight: 800 }}>✦</span>
                <span style={{ flex: 1, textAlign: "left", fontSize: 15.5, color: "var(--text)" }}>roofing companies in New York</span>
                <Link href="/register" className="btn" style={{ borderRadius: 10, padding: "12px 22px" }}>Find leads</Link>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, justifyContent: "center", marginBottom: 32, flexWrap: "wrap" }}>
            <Link href="/register" className="btn btn-lg">Start free</Link>
            <a href="#henry" className="btn btn-ghost btn-lg">◉ Watch demo</a>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14, fontSize: 12.5, color: "var(--text-dim)", flexWrap: "wrap" }}>
            <span>No credit card</span>
            <span style={{ opacity: 0.4 }}>·</span>
            <span>Sources:</span>
            {SOURCES.map((s) => (
              <span key={s} className="glass" style={{ borderRadius: 999, padding: "4px 12px", color: "var(--text-muted)", fontSize: 11.5 }}>{s}</span>
            ))}
          </div>
        </div>

        {/* Henry presence */}
        <div style={{ position: "absolute", right: "max(24px, calc(50% - 590px))", bottom: 40, display: "flex", alignItems: "flex-end", gap: 11 }} className="landing-orb">
          <div className="glass" style={{ borderRadius: "14px 14px 3px 14px", padding: "11px 15px", fontSize: 12.5, color: "var(--text-muted)", maxWidth: 210 }}>
            <span className="gradient-text" style={{ fontWeight: 800 }}>Henry</span> · scoring your leads in real time
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
            {METRICS.map((m) => (
              <div key={m.l}>
                <div className="gradient-text" style={{ fontSize: 21, fontWeight: 800 }}>{m.v}</div>
                <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 2 }}>{m.l}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 28px" }}>
          <div style={{ textAlign: "center", marginBottom: 48 }}>
            <div className="gradient-text" style={eyebrow}>How it works</div>
            <h2 style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.03em", margin: 0 }}>Sentence in, pipeline out</h2>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 18 }}>
            {STEPS.map((s) => (
              <div key={s.n} className="card card-hover" style={{ padding: "26px 24px" }}>
                <div className="brand-mark" style={{ width: 40, height: 40, borderRadius: 12, fontSize: 15, marginBottom: 18 }}>{s.n}</div>
                <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 8 }}>{s.t}</div>
                <div style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--text-muted)" }}>{s.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Feature bento */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 28px" }}>
          <div className="gradient-text" style={eyebrow}>Platform</div>
          <h2 style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 44px" }}>Everything an agency needs to fill the pipeline</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 18 }} className="landing-bento">
            {FEATURES.map((f) => (
              <div
                key={f.t}
                className="card"
                style={{ gridColumn: `span ${f.span}`, position: "relative", overflow: "hidden", border: f.hl ? "1px solid var(--glass-bd2)" : undefined }}
              >
                {f.hl && (
                  <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at top right, var(--soft), transparent 60%)", pointerEvents: "none" }} />
                )}
                <div style={{ position: "relative", fontSize: 17, fontWeight: 800, marginBottom: 8, display: "flex", alignItems: "center", gap: 9 }}>
                  {f.t}
                  {f.hl && <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", color: "#fff", background: "var(--gradient3)", borderRadius: 999, padding: "3px 9px" }}>AI</span>}
                </div>
                <div style={{ position: "relative", fontSize: 13.5, lineHeight: 1.6, color: "var(--text-muted)", marginBottom: 18 }}>{f.d}</div>
                <div style={{ position: "relative", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 12, padding: "13px 15px", fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.7, whiteSpace: "pre-line" }}>{f.ui}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Henry spotlight */}
      <section id="henry" style={{ borderBottom: "1px solid var(--glass-bd)", background: "var(--surface)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "84px 28px", display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 52, alignItems: "center" }} className="landing-henry">
          <div>
            <div className="glass" style={{ display: "inline-flex", alignItems: "center", gap: 9, borderRadius: 999, padding: "7px 16px", fontSize: 13, fontWeight: 800, marginBottom: 20 }}>
              <span className="brand-mark" style={{ width: 24, height: 24, borderRadius: "50%", fontSize: 12 }}>H</span>
              <span className="gradient-text">Henry AI — the star of the show</span>
            </div>
            <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 16px", lineHeight: 1.12 }}>An analyst on the team, not a chatbot in the corner</h2>
            <p style={{ fontSize: 15.5, lineHeight: 1.65, color: "var(--text-muted)", margin: "0 0 24px" }}>Henry reads every lead&apos;s website, reviews and signals, then scores it against your service. Ask for leads, drafts, or a read on your pipeline — he answers with work done.</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {HENRY_POINTS.map((p) => (
                <div key={p} style={{ display: "flex", gap: 12, alignItems: "baseline", fontSize: 14 }}>
                  <span className="gradient-text" style={{ fontWeight: 800 }}>✦</span>
                  {p}
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
                <div style={{ alignSelf: "flex-end", background: "var(--gradient)", color: "#fff", borderRadius: "14px 14px 3px 14px", padding: "11px 15px", fontSize: 13, maxWidth: "85%", lineHeight: 1.5 }}>Find 20 dentists in Austin with weak websites and draft an intro email</div>
                <div style={{ alignSelf: "flex-start", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "14px 14px 14px 3px", padding: "11px 15px", fontSize: 13, maxWidth: "92%", lineHeight: 1.55 }}>
                  Done — 20 dentists found. <b className="gradient-text">7 have weak websites</b> (no SSL, failing mobile checks, or 5+ years stale). Drafts attached:
                </div>
                {CHAT_LEADS.map((cl) => (
                  <div key={cl.name} style={{ display: "flex", alignItems: "center", gap: 12, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 12, padding: "11px 14px" }}>
                    <span style={{ width: 36, height: 36, flexShrink: 0, borderRadius: 10, background: "var(--gradient3)", color: "#fff", display: "grid", placeItems: "center", fontSize: 12.5, fontWeight: 800 }}>{cl.score}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 700 }}>{cl.name}</div>
                      <div style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{cl.signal}</div>
                    </div>
                    <span className="gradient-text" style={{ fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>Draft →</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Integrations */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "80px 28px", textAlign: "center" }}>
          <div className="gradient-text" style={eyebrow}>Integrations</div>
          <h2 style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 12px" }}>Plugged into your stack</h2>
          <p style={{ fontSize: 14.5, color: "var(--text-muted)", margin: "0 auto 40px", maxWidth: 460 }}>Native connectors plus a public API and webhooks for everything else.</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 14, maxWidth: 1000, margin: "0 auto" }}>
            {INTEGRATIONS.map((it) => (
              <div key={it.n} className="card card-hover" style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 16px" }}>
                <span style={{ width: 30, height: 30, borderRadius: 9, background: "var(--surface-2)", border: "1px solid var(--border)", display: "grid", placeItems: "center", color: "var(--text-muted)", fontSize: 12, fontWeight: 800, flexShrink: 0 }}>{it.n[0]}</span>
                <div style={{ textAlign: "left", minWidth: 0 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 700 }}>{it.n}</div>
                  <div style={{ fontSize: 11, color: "var(--text-dim)" }}>{it.g} · <span className="gradient-text" style={{ fontWeight: 700 }}>Connect</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)", background: "var(--surface)" }}>
        <div style={{ maxWidth: 1080, margin: "0 auto", padding: "80px 28px" }}>
          <div style={{ textAlign: "center", marginBottom: 40 }}>
            <div className="gradient-text" style={eyebrow}>Pricing</div>
            <h2 style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 22px" }}>Start free, scale as you grow</h2>
            <div className="seg" style={{ display: "inline-flex" }}>
              <button className={!annual ? "active" : ""} onClick={() => setAnnual(false)} type="button">Monthly</button>
              <button className={annual ? "active" : ""} onClick={() => setAnnual(true)} type="button">Annual −20%</button>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 18, alignItems: "stretch" }} className="landing-pricing">
            {TIERS.map((tier) => (
              <div key={tier.name} style={{ position: "relative" }}>
                {tier.popular && <div style={{ position: "absolute", inset: -1.5, borderRadius: 21, background: "var(--gradient3)", opacity: 0.5, filter: "blur(10px)" }} />}
                <div
                  className="card"
                  style={{
                    position: "relative",
                    padding: "28px 26px",
                    display: "flex",
                    flexDirection: "column",
                    height: "100%",
                    boxSizing: "border-box",
                    border: tier.popular ? "1px solid transparent" : undefined,
                    backgroundClip: tier.popular ? "padding-box" : undefined,
                    boxShadow: tier.popular ? "0 0 0 1.5px var(--neon-a)" : undefined,
                  }}
                >
                  {tier.popular && (
                    <div style={{ position: "absolute", top: -12, left: "50%", transform: "translateX(-50%)", background: "var(--gradient3)", color: "#fff", fontSize: 10.5, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", borderRadius: 999, padding: "4px 14px", whiteSpace: "nowrap" }}>Most popular</div>
                  )}
                  <div style={{ fontSize: 15.5, fontWeight: 800 }}>{tier.name}</div>
                  <div style={{ fontSize: 12.5, color: "var(--text-dim)", margin: "4px 0 20px" }}>{tier.for}</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 5, marginBottom: 22 }}>
                    <span className="gradient-text" style={{ fontSize: 42, fontWeight: 800, letterSpacing: "-0.03em" }}>${price(tier.price)}</span>
                    <span style={{ fontSize: 12.5, color: "var(--text-dim)" }}>/ month</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: 1, marginBottom: 24 }}>
                    {tier.feats.map((ft) => (
                      <div key={ft} style={{ display: "flex", gap: 10, fontSize: 13, color: "var(--text-muted)", alignItems: "baseline" }}>
                        <span style={{ color: "var(--hot)", fontWeight: 800, fontSize: 11 }}>✓</span>
                        {ft}
                      </div>
                    ))}
                  </div>
                  <Link href="/register" className={tier.popular ? "btn" : "btn btn-ghost"} style={{ justifyContent: "center" }}>{tier.cta}</Link>
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
                <div style={{ fontSize: 14.5, lineHeight: 1.6 }}>{q.text}</div>
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
            <div key={tr.t} style={{ display: "flex", gap: 13 }}>
              <span className="glass" style={{ width: 34, height: 34, flexShrink: 0, borderRadius: 10, display: "grid", placeItems: "center", fontSize: 14 }}>{tr.icon}</span>
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 800, marginBottom: 4 }}>{tr.t}</div>
                <div style={{ fontSize: 12.5, lineHeight: 1.55, color: "var(--text-muted)" }}>{tr.d}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section style={{ borderBottom: "1px solid var(--glass-bd)", position: "relative", overflow: "hidden" }}>
        <div className="mesh-bg" />
        <div style={{ position: "relative", maxWidth: 1200, margin: "0 auto", padding: "96px 28px", textAlign: "center" }}>
          <h2 style={{ fontSize: "clamp(34px, 5vw, 56px)", fontWeight: 800, letterSpacing: "-0.04em", margin: "0 0 30px" }}>
            Turn a sentence into
            <br />
            <span className="gradient-text">a sales pipeline.</span>
          </h2>
          <Link href="/register" className="btn btn-lg" style={{ padding: "15px 36px", fontSize: 15.5 }}>Start free</Link>
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 16 }}>No credit card · 50 free leads · Cancel anytime</div>
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
              <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.6, maxWidth: 220 }}>The AI-native lead-gen platform for marketing agencies.</div>
            </div>
            {FOOTER_COLS.map((fc) => (
              <div key={fc.t}>
                <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-dim)", marginBottom: 14 }}>{fc.t}</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                  {fc.links.map((fl) => (
                    <a key={fl} href="#" style={{ fontSize: 13, color: "var(--text-muted)" }}>{fl}</a>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div style={{ borderTop: "1px solid var(--glass-bd)", paddingTop: 20, display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, color: "var(--text-dim)", flexWrap: "wrap", gap: 12 }}>
            <span>© 2026 Convioo. All rights reserved.</span>
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

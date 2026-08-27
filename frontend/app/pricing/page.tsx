"use client";

import Link from "next/link";
import { Icon, type IconName } from "@/components/Icon";
import { PublicPageShell } from "@/components/PublicPageShell";
import { useLocale, type TranslationKey } from "@/lib/i18n";

interface Tier {
  id: "free" | "pro" | "team";
  highlight?: boolean;
  icon: IconName;
  accent: string;
  priceKey: TranslationKey;
  perKey: TranslationKey;
  ctaKey: TranslationKey;
  features: TranslationKey[];
}

const TIERS: Tier[] = [
  {
    id: "free",
    icon: "sparkles",
    accent: "var(--text-muted)",
    priceKey: "pricing.free.price",
    perKey: "pricing.free.per",
    ctaKey: "pricing.free.cta",
    features: [
      "pricing.feat.searches5",
      "pricing.feat.aiScore",
      "pricing.feat.henryConsult",
      "pricing.feat.crmBasic",
    ],
  },
  {
    id: "pro",
    icon: "zap",
    accent: "var(--accent)",
    highlight: true,
    priceKey: "pricing.pro.price",
    perKey: "pricing.pro.per",
    ctaKey: "pricing.pro.cta",
    features: [
      "pricing.feat.searches200",
      "pricing.feat.aiScore",
      "pricing.feat.exportCsv",
      "pricing.feat.outreachTemplates",
      "pricing.feat.customFields",
      "pricing.feat.dailyDigest",
    ],
  },
  {
    id: "team",
    icon: "users",
    accent: "#16A34A",
    priceKey: "pricing.team.price",
    perKey: "pricing.team.per",
    ctaKey: "pricing.team.cta",
    features: [
      "pricing.feat.team5",
      "pricing.feat.searchesTeam",
      "pricing.feat.sharedCrm",
      "pricing.feat.dedupTeam",
      "pricing.feat.activityFeed",
      "pricing.feat.henryTeam",
    ],
  },
];

export default function PricingPage() {
  const { t } = useLocale();
  return (
    <PublicPageShell width={1080}>
      <div style={{ textAlign: "center", marginBottom: 48 }}>
        <h1
          style={{
            fontSize: 44,
            fontWeight: 800,
            letterSpacing: "-0.02em",
            margin: "0 0 12px",
          }}
        >
          {t("pricing.headline")}
        </h1>
        <div
          style={{
            fontSize: 16,
            color: "var(--text-muted)",
            maxWidth: 620,
            margin: "0 auto",
            lineHeight: 1.5,
          }}
        >
          {t("pricing.subhead")}
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: 16,
          marginBottom: 64,
        }}
      >
        {TIERS.map((tier) => (
          <div
            key={tier.id}
            className="card"
            style={{
              padding: 24,
              border: tier.highlight
                ? "2px solid var(--accent)"
                : "1px solid var(--border)",
              position: "relative",
            }}
          >
            {tier.highlight && (
              <div
                style={{
                  position: "absolute",
                  top: -12,
                  right: 16,
                  background: "var(--accent)",
                  color: "white",
                  borderRadius: 6,
                  padding: "3px 10px",
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                }}
              >
                {t("pricing.popular")}
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Icon name={tier.icon} size={18} style={{ color: tier.accent }} />
              <div style={{ fontSize: 16, fontWeight: 700 }}>
                {t(`pricing.${tier.id}.name` as TranslationKey)}
              </div>
            </div>
            <div
              style={{
                fontSize: 13,
                color: "var(--text-muted)",
                marginTop: 4,
                marginBottom: 16,
              }}
            >
              {t(`pricing.${tier.id}.tagline` as TranslationKey)}
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <div
                style={{
                  fontSize: 36,
                  fontWeight: 800,
                  letterSpacing: "-0.02em",
                }}
              >
                {t(tier.priceKey)}
              </div>
              <div style={{ fontSize: 13, color: "var(--text-dim)" }}>
                {t(tier.perKey)}
              </div>
            </div>

            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: "20px 0 24px",
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              {tier.features.map((f) => (
                <li
                  key={f}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 8,
                    fontSize: 13.5,
                  }}
                >
                  <Icon
                    name="check"
                    size={14}
                    style={{ color: tier.accent, marginTop: 2, flexShrink: 0 }}
                  />
                  <span>{t(f)}</span>
                </li>
              ))}
            </ul>
            <Link
              href="/register"
              className={
                tier.highlight ? "btn btn-sm" : "btn btn-ghost btn-sm"
              }
              style={{ width: "100%", justifyContent: "center" }}
            >
              {t(tier.ctaKey)}
            </Link>
          </div>
        ))}
      </div>

      <div
        className="card"
        style={{
          padding: 28,
          textAlign: "center",
          background: "var(--surface-2)",
        }}
      >
        <h2 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 8px" }}>
          {t("pricing.faq.title")}
        </h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: 20,
            marginTop: 24,
            textAlign: "left",
          }}
        >
          <FaqItem qKey="pricing.faq.q1" aKey="pricing.faq.a1" />
          <FaqItem qKey="pricing.faq.q2" aKey="pricing.faq.a2" />
          <FaqItem qKey="pricing.faq.q3" aKey="pricing.faq.a3" />
          <FaqItem qKey="pricing.faq.q4" aKey="pricing.faq.a4" />
        </div>
      </div>
    </PublicPageShell>
  );
}

function FaqItem({
  qKey,
  aKey,
}: {
  qKey: TranslationKey;
  aKey: TranslationKey;
}) {
  const { t } = useLocale();
  return (
    <div>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>
        {t(qKey)}
      </div>
      <div style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.6 }}>
        {t(aKey)}
      </div>
    </div>
  );
}

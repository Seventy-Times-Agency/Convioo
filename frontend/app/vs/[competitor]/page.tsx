"use client";

import { notFound, useParams } from "next/navigation";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { PublicPageShell } from "@/components/PublicPageShell";
import { useLocale, type TranslationKey } from "@/lib/i18n";

const COMPETITORS = ["apollo", "clay", "lusha"] as const;
type Competitor = (typeof COMPETITORS)[number];

function isCompetitor(value: string): value is Competitor {
  return (COMPETITORS as readonly string[]).includes(value);
}

export default function VsPage() {
  const { t } = useLocale();
  const params = useParams<{ competitor: string }>();
  const slug = params?.competitor ?? "";
  if (!isCompetitor(slug)) {
    notFound();
  }
  const c = slug as Competitor;
  const competitorName = t(`vs.${c}.name` as TranslationKey);

  const ROWS: {
    labelKey: TranslationKey;
    convioo: TranslationKey;
    competitor: TranslationKey;
  }[] = [
    {
      labelKey: "vs.row.pricing",
      convioo: "vs.convioo.pricing",
      competitor: `vs.${c}.pricing` as TranslationKey,
    },
    {
      labelKey: "vs.row.aiScore",
      convioo: "vs.convioo.aiScore",
      competitor: `vs.${c}.aiScore` as TranslationKey,
    },
    {
      labelKey: "vs.row.crm",
      convioo: "vs.convioo.crm",
      competitor: `vs.${c}.crm` as TranslationKey,
    },
    {
      labelKey: "vs.row.assistant",
      convioo: "vs.convioo.assistant",
      competitor: `vs.${c}.assistant` as TranslationKey,
    },
    {
      labelKey: "vs.row.dataSource",
      convioo: "vs.convioo.dataSource",
      competitor: `vs.${c}.dataSource` as TranslationKey,
    },
    {
      labelKey: "vs.row.audience",
      convioo: "vs.convioo.audience",
      competitor: `vs.${c}.audience` as TranslationKey,
    },
  ];

  return (
    <PublicPageShell width={1000}>
      <div style={{ marginBottom: 40, textAlign: "center" }}>
        <div
          className="eyebrow"
          style={{ marginBottom: 8, color: "var(--accent)" }}
        >
          {t("vs.eyebrow")}
        </div>
        <h1
          style={{
            fontSize: 40,
            fontWeight: 800,
            letterSpacing: "-0.02em",
            margin: "0 0 10px",
          }}
        >
          {t("vs.headline", { competitor: competitorName })}
        </h1>
        <div
          style={{
            fontSize: 15,
            color: "var(--text-muted)",
            maxWidth: 620,
            margin: "0 auto",
            lineHeight: 1.5,
          }}
        >
          {t(`vs.${c}.subhead` as TranslationKey)}
        </div>
      </div>

      <div
        className="card"
        style={{
          padding: 0,
          overflow: "hidden",
          marginBottom: 40,
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr
              style={{
                background: "var(--surface-2)",
                fontSize: 12,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}
            >
              <th
                style={{
                  padding: "14px 18px",
                  textAlign: "left",
                  color: "var(--text-dim)",
                  width: "30%",
                }}
              >
                {t("vs.col.feature")}
              </th>
              <th
                style={{
                  padding: "14px 18px",
                  textAlign: "left",
                  color: "var(--accent)",
                }}
              >
                Convioo
              </th>
              <th
                style={{
                  padding: "14px 18px",
                  textAlign: "left",
                  color: "var(--text-muted)",
                }}
              >
                {competitorName}
              </th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr
                key={row.labelKey}
                style={{ borderTop: "1px solid var(--border)" }}
              >
                <td
                  style={{
                    padding: "14px 18px",
                    fontSize: 13.5,
                    color: "var(--text-muted)",
                  }}
                >
                  {t(row.labelKey)}
                </td>
                <td
                  style={{
                    padding: "14px 18px",
                    fontSize: 14,
                    color: "var(--text)",
                  }}
                >
                  {t(row.convioo)}
                </td>
                <td
                  style={{
                    padding: "14px 18px",
                    fontSize: 14,
                    color: "var(--text-muted)",
                  }}
                >
                  {t(row.competitor)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div
        className="card"
        style={{
          padding: 28,
          background: "var(--surface-2)",
          textAlign: "center",
        }}
      >
        <h2 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 8px" }}>
          {t("vs.cta.title", { competitor: competitorName })}
        </h2>
        <div
          style={{
            fontSize: 14,
            color: "var(--text-muted)",
            marginBottom: 18,
          }}
        >
          {t("vs.cta.body")}
        </div>
        <div
          style={{
            display: "flex",
            gap: 8,
            justifyContent: "center",
            flexWrap: "wrap",
          }}
        >
          <Link href="/register" className="btn btn-sm">
            <Icon name="sparkles" size={13} />
            {t("vs.cta.start")}
          </Link>
          <Link href="/pricing" className="btn btn-ghost btn-sm">
            {t("vs.cta.pricing")}
          </Link>
        </div>
      </div>
    </PublicPageShell>
  );
}

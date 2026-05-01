"use client";

import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { ApiError, getAnalytics, type Analytics } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

/**
 * /app/analytics — outreach + lead-gen activity at a glance.
 *
 * Reads pre-aggregated counts from /api/v1/users/{id}/analytics so
 * the page is one round-trip. Charts are pure-CSS bar columns over
 * the 30-day series — no chart library, no extra bundle.
 */
export default function AnalyticsPage() {
  const { t } = useLocale();
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAnalytics()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <Topbar
        title={t("analytics.title")}
        subtitle={t("analytics.subtitle")}
      />
      <div className="page" style={{ maxWidth: 1100 }}>
        {error && (
          <div
            className="card"
            style={{ padding: 16, marginBottom: 14, color: "var(--cold)" }}
          >
            {error}
          </div>
        )}
        {!data && !error && (
          <div className="card" style={{ padding: 24 }}>
            {t("common.loading")}
          </div>
        )}
        {data && (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                gap: 12,
                marginBottom: 18,
              }}
            >
              <Stat
                icon="folder"
                label={t("analytics.leadsTotal")}
                value={data.leads_total}
                hint={`+${data.leads_last_30d} ${t("analytics.in30d")}`}
              />
              <Stat
                icon="sparkles"
                label={t("analytics.sessionsTotal")}
                value={data.sessions_total}
                hint={`+${data.sessions_last_30d} ${t("analytics.in30d")}`}
              />
              <Stat
                icon="send"
                label={t("analytics.emailsSent")}
                value={data.emails_sent_total}
                hint={`+${data.emails_sent_last_30d} ${t("analytics.in30d")}`}
              />
              <Stat
                icon="mail"
                label={t("analytics.abSplit")}
                value={`${data.emails_variant_a} / ${data.emails_variant_b}`}
                hint="A / B"
              />
            </div>

            <div className="card" style={{ padding: 24, marginBottom: 14 }}>
              <div
                className="eyebrow"
                style={{ marginBottom: 14 }}
              >
                {t("analytics.daily")}
              </div>
              <SparklineBars points={data.daily} />
              <div
                style={{
                  display: "flex",
                  gap: 16,
                  fontSize: 11,
                  color: "var(--text-dim)",
                  marginTop: 10,
                }}
              >
                <span>
                  <span
                    style={{
                      display: "inline-block",
                      width: 10,
                      height: 10,
                      background: "var(--accent)",
                      borderRadius: 2,
                      marginRight: 6,
                      verticalAlign: "-1px",
                    }}
                  />
                  {t("analytics.legendLeads")}
                </span>
                <span>
                  <span
                    style={{
                      display: "inline-block",
                      width: 10,
                      height: 10,
                      background: "var(--hot)",
                      borderRadius: 2,
                      marginRight: 6,
                      verticalAlign: "-1px",
                    }}
                  />
                  {t("analytics.legendSent")}
                </span>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 12,
              }}
            >
              <div className="card" style={{ padding: 24 }}>
                <div className="eyebrow" style={{ marginBottom: 12 }}>
                  {t("analytics.statusBreakdown")}
                </div>
                {data.status_counts.length === 0 ? (
                  <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                    {t("analytics.empty")}
                  </div>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                    }}
                  >
                    {data.status_counts.map((s) => (
                      <Row
                        key={s.status}
                        label={t(
                          `lead.statusLabel.${s.status}` as never,
                        ) as string}
                        value={s.count}
                      />
                    ))}
                  </div>
                )}
              </div>

              <div className="card" style={{ padding: 24 }}>
                <div className="eyebrow" style={{ marginBottom: 12 }}>
                  {t("analytics.topNiches")}
                </div>
                {data.top_niches.length === 0 ? (
                  <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                    {t("analytics.empty")}
                  </div>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                    }}
                  >
                    {data.top_niches.map((n, i) => (
                      <Row
                        key={`${n.niche}-${n.region}-${i}`}
                        label={`${n.niche} · ${n.region}`}
                        value={n.count}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function Stat({
  icon,
  label,
  value,
  hint,
}: {
  icon: "folder" | "sparkles" | "send" | "mail";
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="card" style={{ padding: 18 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          color: "var(--text-muted)",
          fontSize: 12,
          marginBottom: 8,
        }}
      >
        <Icon name={icon} size={13} />
        {label}
      </div>
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 28,
          fontWeight: 700,
          letterSpacing: "-0.02em",
        }}
      >
        {value}
      </div>
      {hint && (
        <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>
          {hint}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "6px 0",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <span style={{ fontSize: 13 }}>{label}</span>
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 13,
          fontWeight: 600,
        }}
      >
        {value}
      </span>
    </div>
  );
}

function SparklineBars({
  points,
}: {
  points: { date: string; leads: number; emails_sent: number }[];
}) {
  // Stack two series side-by-side per day. Height is normalised to
  // the larger of the two maxima so leads dominate visually if they
  // dwarf sends.
  const maxLeads = Math.max(1, ...points.map((p) => p.leads));
  const maxSent = Math.max(1, ...points.map((p) => p.emails_sent));
  const max = Math.max(maxLeads, maxSent);
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-end",
        gap: 3,
        height: 120,
      }}
    >
      {points.map((p) => (
        <div
          key={p.date}
          title={`${p.date}\nleads: ${p.leads}\nsent: ${p.emails_sent}`}
          style={{
            flex: 1,
            display: "flex",
            alignItems: "flex-end",
            gap: 2,
            height: "100%",
          }}
        >
          <div
            style={{
              flex: 1,
              background: "var(--accent)",
              borderRadius: 2,
              height: `${(p.leads / max) * 100}%`,
              minHeight: p.leads > 0 ? 2 : 0,
              opacity: 0.85,
            }}
          />
          <div
            style={{
              flex: 1,
              background: "var(--hot)",
              borderRadius: 2,
              height: `${(p.emails_sent / max) * 100}%`,
              minHeight: p.emails_sent > 0 ? 2 : 0,
              opacity: 0.85,
            }}
          />
        </div>
      ))}
    </div>
  );
}

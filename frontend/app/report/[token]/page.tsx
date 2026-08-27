"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ApiError,
  type PublicReport,
  getPublicReport,
  publicReportPdfUrl,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";

/**
 * Wave 4 — public, white-labelled client report.
 *
 * Lives OUTSIDE the /app shell: no auth, no sidebar, no RequireAuth.
 * The link is tokenised and meant to be forwarded to the agency's own
 * clients. Branding (logo / name / accent colour) is supplied by the
 * backend; the page chrome is i18n via the shared LocaleProvider that
 * wraps the whole app from the root layout.
 */

const DEFAULT_ACCENT = "#6366F1";

function fmtScore(score: number | null): string {
  if (score === null || Number.isNaN(score)) return "—";
  return String(Math.round(score));
}

export default function PublicReportPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const { t } = useLocale();

  const [report, setReport] = useState<PublicReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [gone, setGone] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPublicReport(token)
      .then((r) => {
        if (cancelled) return;
        setReport(r);
      })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setGone(true);
        } else {
          setError(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (loading) {
    return (
      <Shell accent={DEFAULT_ACCENT}>
        <div style={{ padding: 48, textAlign: "center", color: "var(--text-muted)" }}>
          {t("common.loading")}
        </div>
      </Shell>
    );
  }

  if (gone) {
    return (
      <Shell accent={DEFAULT_ACCENT}>
        <div
          style={{
            padding: "64px 24px",
            textAlign: "center",
            maxWidth: 420,
            margin: "0 auto",
          }}
        >
          <div style={{ fontSize: 19, fontWeight: 700, marginBottom: 8 }}>
            {t("report.gone.title")}
          </div>
          <div style={{ fontSize: 14, color: "var(--text-muted)", lineHeight: 1.55 }}>
            {t("report.gone.body")}
          </div>
        </div>
      </Shell>
    );
  }

  if (error || !report) {
    return (
      <Shell accent={DEFAULT_ACCENT}>
        <div
          style={{
            padding: "64px 24px",
            textAlign: "center",
            color: "var(--cold)",
          }}
        >
          {t("report.error")}
        </div>
      </Shell>
    );
  }

  const accent =
    report.brand_color && /^#[0-9a-fA-F]{6}$/.test(report.brand_color)
      ? report.brand_color
      : DEFAULT_ACCENT;
  const s = report.stats;

  return (
    <Shell accent={accent}>
      {/* ---- Branded header ---- */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          paddingBottom: 24,
          borderBottom: `2px solid ${accent}`,
          marginBottom: 28,
          flexWrap: "wrap",
        }}
      >
        {report.brand_logo && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={report.brand_logo}
            alt={report.brand_name ?? "logo"}
            style={{ height: 48, width: "auto", objectFit: "contain" }}
          />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          {report.brand_name && (
            <div style={{ fontSize: 13, fontWeight: 600, color: accent }}>
              {report.brand_name}
            </div>
          )}
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: "2px 0 0" }}>
            {report.title || t("report.defaultTitle")}
          </h1>
          {(s.niche || s.region) && (
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>
              {[s.niche, s.region].filter(Boolean).join(" — ")}
            </div>
          )}
        </div>
        <a
          className="btn btn-sm"
          href={publicReportPdfUrl(token)}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            background: accent,
            borderColor: accent,
            color: "#fff",
          }}
        >
          {t("report.downloadPdf")}
        </a>
      </header>

      {/* ---- Stats row ---- */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
          gap: 12,
          marginBottom: 28,
        }}
      >
        <Stat label={t("report.stat.total")} value={s.total_leads} accent={accent} />
        <Stat label={t("report.stat.hot")} value={s.hot_leads} accent={accent} />
        <Stat
          label={t("report.stat.withEmail")}
          value={s.leads_with_email}
          accent={accent}
        />
        <Stat label={t("report.stat.replied")} value={s.replied} accent={accent} />
        <Stat
          label={t("report.stat.avgScore")}
          value={fmtScore(s.avg_score)}
          accent={accent}
        />
      </div>

      {/* ---- Insights ---- */}
      {s.insights && (
        <div
          style={{
            padding: 16,
            borderRadius: 12,
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            fontSize: 14,
            lineHeight: 1.6,
            marginBottom: 28,
          }}
        >
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            {t("report.insights")}
          </div>
          {s.insights}
        </div>
      )}

      {/* ---- Top leads ---- */}
      <div className="eyebrow" style={{ marginBottom: 12 }}>
        {t("report.topLeads")}
      </div>
      {s.top_leads.length === 0 ? (
        <div style={{ fontSize: 13.5, color: "var(--text-muted)" }}>
          {t("report.topLeads.empty")}
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 13.5,
              minWidth: 520,
            }}
          >
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-muted)" }}>
                <th style={{ padding: "8px 10px", fontWeight: 600 }}>
                  {t("report.col.name")}
                </th>
                <th style={{ padding: "8px 10px", fontWeight: 600 }}>
                  {t("report.col.score")}
                </th>
                <th style={{ padding: "8px 10px", fontWeight: 600 }}>
                  {t("report.col.status")}
                </th>
                <th style={{ padding: "8px 10px", fontWeight: 600 }}>
                  {t("report.col.contact")}
                </th>
              </tr>
            </thead>
            <tbody>
              {s.top_leads.map((lead, i) => (
                <tr
                  key={i}
                  style={{ borderTop: "1px solid var(--border)" }}
                >
                  <td style={{ padding: "10px", fontWeight: 600 }}>
                    {lead.website ? (
                      <a
                        href={lead.website}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: accent, textDecoration: "none" }}
                      >
                        {lead.name || t("report.col.unnamed")}
                      </a>
                    ) : (
                      lead.name || t("report.col.unnamed")
                    )}
                  </td>
                  <td style={{ padding: "10px" }}>
                    <span
                      style={{
                        display: "inline-block",
                        minWidth: 28,
                        padding: "2px 8px",
                        borderRadius: 999,
                        fontSize: 12.5,
                        fontWeight: 600,
                        background: `color-mix(in srgb, ${accent} 14%, transparent)`,
                        color: accent,
                      }}
                    >
                      {fmtScore(lead.score)}
                    </span>
                  </td>
                  <td style={{ padding: "10px", color: "var(--text-muted)" }}>
                    {lead.lead_status || "—"}
                  </td>
                  <td style={{ padding: "10px", color: "var(--text-muted)" }}>
                    {lead.contact_email || lead.phone || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <footer
        style={{
          marginTop: 36,
          paddingTop: 16,
          borderTop: "1px solid var(--border)",
          fontSize: 12,
          color: "var(--text-muted)",
          textAlign: "center",
        }}
      >
        {report.generated_at
          ? t("report.generatedOn", {
              date: new Date(report.generated_at).toLocaleString(),
            })
          : t("report.footer")}
      </footer>
    </Shell>
  );
}

function Shell({
  accent,
  children,
}: {
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg)",
        color: "var(--text)",
        // expose accent as a CSS var for any descendant that wants it
        // (kept inline-scoped, no global pollution)
        ["--report-accent" as string]: accent,
      }}
    >
      <div
        style={{
          maxWidth: 880,
          margin: "0 auto",
          padding: "40px 20px 64px",
        }}
      >
        {children}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent: string;
}) {
  return (
    <div
      style={{
        padding: 14,
        borderRadius: 12,
        background: "var(--surface)",
        border: "1px solid var(--border)",
      }}
    >
      <div style={{ fontSize: 24, fontWeight: 700, color: accent }}>{value}</div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
        {label}
      </div>
    </div>
  );
}

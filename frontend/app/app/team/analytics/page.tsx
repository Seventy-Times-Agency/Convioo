"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { BarList, DualLine } from "@/components/app/MiniChart";
import {
  ApiError,
  getTeamAnalytics,
  type TeamAnalytics,
} from "@/lib/api";
import { getActiveWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";

/**
 * Owner-only per-team analytics. Reads the active workspace; if the
 * user is in personal mode (no team selected) we redirect them back
 * to /app/team. Backend gates the endpoint on owner-role, so a
 * non-owner viewer sees the toast-style error rather than the page.
 */
export default function TeamAnalyticsPage() {
  const { t } = useLocale();
  const router = useRouter();
  const [data, setData] = useState<TeamAnalytics | null>(null);
  const [days, setDays] = useState<7 | 30 | 90>(30);

  useEffect(() => {
    const ws = getActiveWorkspace();
    if (ws.kind !== "team") {
      router.replace("/app/team");
      return;
    }
    let cancelled = false;
    setData(null);
    const to = new Date();
    const from = new Date(to.getTime() - days * 24 * 60 * 60 * 1000);
    getTeamAnalytics(ws.team_id, {
      from: from.toISOString(),
      to: to.toISOString(),
    })
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 403) {
          showError(t("team.analytics.ownerOnly"));
          return;
        }
        showError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [router, days, t]);

  return (
    <>
      <Topbar
        title={t("team.analytics.title")}
        subtitle={t("team.analytics.subtitle")}
      />
      <div className="page" style={{ maxWidth: 1100 }}>
        <div
          style={{
            display: "flex",
            gap: 8,
            marginBottom: 16,
            alignItems: "center",
          }}
        >
          <span
            style={{
              fontSize: 12,
              color: "var(--text-dim)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            {t("team.analytics.range")}
          </span>
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              type="button"
              className={days === d ? "btn btn-primary" : "btn"}
              style={{ padding: "4px 10px", fontSize: 12 }}
              onClick={() => setDays(d as 7 | 30 | 90)}
            >
              {t("team.analytics.days", { n: d })}
            </button>
          ))}
        </div>

        {!data && (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {t("common.loading")}
          </div>
        )}

        {data && (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                gap: 12,
                marginBottom: 18,
              }}
            >
              <Tile label={t("team.analytics.tile.searches")} value={data.searches_total} />
              <Tile label={t("team.analytics.tile.leads")} value={data.leads_total} />
              <Tile
                label={t("team.analytics.tile.avgScore")}
                value={data.avg_lead_score ?? t("common.none")}
              />
              <Tile
                label={t("team.analytics.tile.costPerLead")}
                value={
                  data.avg_lead_cost_usd !== null
                    ? `$${data.avg_lead_cost_usd}`
                    : t("common.none")
                }
              />
            </div>

            <div className="card" style={{ padding: 18, marginBottom: 12 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>
                {t("team.analytics.activityByDay")}
              </div>
              <DualLine
                points={data.timeseries.map((p) => ({
                  label: p.date,
                  a: p.searches_total,
                  b: p.leads_total,
                }))}
                aLabel={t("team.analytics.tile.searches")}
                bLabel={t("team.analytics.tile.leads")}
              />
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 12,
                marginBottom: 12,
              }}
            >
              <Card title={t("team.analytics.statusBreakdown")}>
                <BarList
                  items={data.status_breakdown.map((b) => ({
                    label: b.status,
                    value: b.leads_count,
                  }))}
                />
              </Card>
              <Card title={t("team.analytics.topSources")}>
                <BarList
                  items={data.sources.map((b) => ({
                    label: b.source,
                    value: b.leads_count,
                  }))}
                />
              </Card>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 12,
                marginBottom: 12,
              }}
            >
              <Card title={t("team.analytics.topNiches")}>
                <BarList
                  items={data.niches.map((b) => ({
                    label: b.niche,
                    value: b.searches_total,
                  }))}
                />
              </Card>
              <Card title={t("team.analytics.memberActivity")}>
                <BarList
                  items={data.members.map((m) => ({
                    label: m.name,
                    value: m.leads_total,
                    hint: t("team.analytics.memberHint", {
                      searches: m.searches_total,
                      hot: m.hot_leads,
                    }),
                  }))}
                />
              </Card>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function Tile({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div className="card" style={{ padding: "16px 18px" }}>
      <div
        style={{
          fontSize: 11,
          color: "var(--text-dim)",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          marginBottom: 6,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 24,
          fontWeight: 700,
          letterSpacing: "-0.02em",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
    </div>
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card" style={{ padding: 18 }}>
      <div className="eyebrow" style={{ marginBottom: 10 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

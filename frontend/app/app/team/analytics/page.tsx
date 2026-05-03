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

/**
 * Owner-only per-team analytics. Reads the active workspace; if the
 * user is in personal mode (no team selected) we redirect them back
 * to /app/team. Backend gates the endpoint on owner-role, so a
 * non-owner viewer sees the toast-style error rather than the page.
 */
export default function TeamAnalyticsPage() {
  const router = useRouter();
  const [data, setData] = useState<TeamAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState<7 | 30 | 90>(30);

  useEffect(() => {
    const ws = getActiveWorkspace();
    if (ws.kind !== "team") {
      router.replace("/app/team");
      return;
    }
    let cancelled = false;
    setData(null);
    setError(null);
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
          setError("Аналітика доступна лише власнику команди.");
          return;
        }
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [router, days]);

  return (
    <>
      <Topbar
        title="Аналітика команди"
        subtitle="Поведінка команди в обраному діапазоні. Тільки для власника."
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
            Діапазон
          </span>
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              type="button"
              className={days === d ? "btn btn-primary" : "btn"}
              style={{ padding: "4px 10px", fontSize: 12 }}
              onClick={() => setDays(d as 7 | 30 | 90)}
            >
              {d}д
            </button>
          ))}
        </div>

        {error && (
          <div
            className="card"
            style={{
              padding: 14,
              color: "var(--cold)",
              borderColor: "var(--cold)",
              marginBottom: 16,
            }}
          >
            {error}
          </div>
        )}

        {!error && !data && (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Завантаження…
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
              <Tile label="Пошуків" value={data.searches_total} />
              <Tile label="Лідів" value={data.leads_total} />
              <Tile
                label="Середній скор"
                value={data.avg_lead_score ?? "—"}
              />
              <Tile
                label="Cost / lead"
                value={
                  data.avg_lead_cost_usd !== null
                    ? `$${data.avg_lead_cost_usd}`
                    : "—"
                }
              />
            </div>

            <div className="card" style={{ padding: 18, marginBottom: 12 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>
                Активність по днях
              </div>
              <DualLine
                points={data.timeseries.map((p) => ({
                  label: p.date,
                  a: p.searches_total,
                  b: p.leads_total,
                }))}
                aLabel="Пошуки"
                bLabel="Ліди"
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
              <Card title="Розподіл по статусах">
                <BarList
                  items={data.status_breakdown.map((b) => ({
                    label: b.status,
                    value: b.leads_count,
                  }))}
                />
              </Card>
              <Card title="Топ джерела">
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
              <Card title="Топ ніші">
                <BarList
                  items={data.niches.map((b) => ({
                    label: b.niche,
                    value: b.searches_total,
                  }))}
                />
              </Card>
              <Card title="Активність учасників">
                <BarList
                  items={data.members.map((m) => ({
                    label: m.name,
                    value: m.leads_total,
                    hint: `${m.searches_total} пошуків · ${m.hot_leads} hot`,
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

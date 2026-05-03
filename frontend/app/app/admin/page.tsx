"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { ApiError, getAdminOverview, type AdminOverview } from "@/lib/api";

/**
 * Admin-only ops dashboard. The backend gates ``/api/v1/admin/overview``
 * with ``is_admin`` and returns 404 to non-admins, so we mirror that
 * here: a 404 from the API redirects the user back to /app — they
 * shouldn't even know the route exists.
 */
export default function AdminPage() {
  const router = useRouter();
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAdminOverview()
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          router.replace("/app");
          return;
        }
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <>
      <Topbar
        title="Админ-панель"
        subtitle="Платформенные метрики, видны только администраторам."
      />
      <div className="page" style={{ maxWidth: 1100 }}>
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

        {data === null && !error ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
        ) : data ? (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                gap: 12,
                marginBottom: 18,
              }}
            >
              <Tile label="Всего пользователей" value={data.users_total} />
              <Tile label="Платных" value={data.users_paid} accent="var(--accent)" />
              <Tile label="На триале" value={data.users_trialing} />
              <Tile label="Команд" value={data.teams_total} />
              <Tile
                label="Поисков за 7 дней"
                value={data.searches_last_7d}
              />
              <Tile
                label="Поисков выполняется"
                value={data.searches_running}
                accent={data.searches_running > 0 ? "#16A34A" : undefined}
              />
              <Tile
                label="Лидов за 7 дней"
                value={data.leads_last_7d}
              />
              <Tile
                label="Failed поисков 24ч"
                value={data.failed_searches_last_24h}
                accent={data.failed_searches_last_24h > 0 ? "#EF4444" : undefined}
              />
            </div>

            <div className="card" style={{ padding: 18 }}>
              <div className="eyebrow" style={{ marginBottom: 12 }}>
                Top users by queries
              </div>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 13,
                }}
              >
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--text-dim)" }}>
                    <th style={{ padding: "6px 8px" }}>ID</th>
                    <th style={{ padding: "6px 8px" }}>Name</th>
                    <th style={{ padding: "6px 8px" }}>Email</th>
                    <th style={{ padding: "6px 8px" }}>Plan</th>
                    <th style={{ padding: "6px 8px", textAlign: "right" }}>
                      Queries
                    </th>
                    <th style={{ padding: "6px 8px" }}>Admin?</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_users_by_searches.map((u) => (
                    <tr
                      key={u.user_id}
                      style={{ borderTop: "1px solid var(--border)" }}
                    >
                      <td
                        style={{
                          padding: "6px 8px",
                          fontFamily: "var(--font-mono)",
                          color: "var(--text-dim)",
                        }}
                      >
                        {u.user_id}
                      </td>
                      <td style={{ padding: "6px 8px" }}>{u.name}</td>
                      <td
                        style={{
                          padding: "6px 8px",
                          color: "var(--text-muted)",
                        }}
                      >
                        {u.email ?? "—"}
                      </td>
                      <td style={{ padding: "6px 8px" }}>{u.plan}</td>
                      <td
                        style={{
                          padding: "6px 8px",
                          textAlign: "right",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {u.queries_used}
                      </td>
                      <td style={{ padding: "6px 8px" }}>
                        {u.is_admin ? "✓" : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>
    </>
  );
}

function Tile({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: string;
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
          fontSize: 28,
          fontWeight: 700,
          letterSpacing: "-0.02em",
          color: accent ?? "var(--text)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { BarList } from "@/components/app/MiniChart";
import {
  ApiError,
  getAdminQuality,
  getAdminSourcesHealth,
  type AdminQuality,
  type SourceHealthEntry,
} from "@/lib/api";

/**
 * Admin quality / ops dashboard. Deliberately NOT a business view —
 * no MRR, no revenue, no user counts. The job is to surface platform
 * health: Anthropic spend, error rate, queue depth, slowest searches,
 * external-source health. Backend gates ``/api/v1/admin/*`` with the
 * ``is_admin`` flag and 404s non-admins so the route appears to
 * not exist for everyone else.
 */
export default function AdminPage() {
  const router = useRouter();
  const [quality, setQuality] = useState<AdminQuality | null>(null);
  const [sources, setSources] = useState<SourceHealthEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getAdminQuality(), getAdminSourcesHealth()])
      .then(([q, s]) => {
        if (cancelled) return;
        setQuality(q);
        setSources(s.sources);
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
        title="Адмін · якість"
        subtitle="Сигнали якості платформи: Anthropic spend, помилки, черга, повільні пошуки, здоров’я джерел."
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

        {!error && !quality && (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Завантаження…
          </div>
        )}

        {quality && (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                gap: 12,
                marginBottom: 18,
              }}
            >
              <Tile
                label="Anthropic ~ spend"
                value={`$${quality.anthropic_estimated_spend_usd.toFixed(2)}`}
                hint={`${quality.anthropic_calls_total.toLocaleString()} викликів · ${quality.anthropic_calls_failed} fail`}
                accent={quality.anthropic_calls_failed > 0 ? "#EF4444" : undefined}
              />
              <Tile
                label="Failure rate · 24h"
                value={`${(quality.searches_failure_rate_24h * 100).toFixed(1)}%`}
                hint={`${quality.searches_failed_24h} / ${quality.searches_total_24h}`}
                accent={
                  quality.searches_failure_rate_24h > 0.1 ? "#EF4444" : undefined
                }
              />
              <Tile
                label="Queue depth"
                value={`${quality.queue_pending + quality.queue_running}`}
                hint={`${quality.queue_pending} pending · ${quality.queue_running} running`}
                accent={
                  quality.queue_running > 5 ? "#EAB308" : undefined
                }
              />
              <Tile
                label="Searches · 24h"
                value={quality.searches_total_24h}
              />
            </div>

            <div className="card" style={{ padding: 18, marginBottom: 12 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>
                Source health
              </div>
              {sources && sources.length > 0 ? (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(2, 1fr)",
                    gap: 8,
                  }}
                >
                  {sources.map((s) => (
                    <div
                      key={s.source}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        padding: "8px 12px",
                        border: "1px solid var(--border)",
                        borderRadius: 6,
                        fontSize: 13,
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600 }}>{s.source}</div>
                        {s.detail && (
                          <div
                            style={{
                              fontSize: 11,
                              color: "var(--text-dim)",
                            }}
                          >
                            {s.detail}
                          </div>
                        )}
                      </div>
                      <div
                        style={{
                          textAlign: "right",
                          color: statusColor(s.status),
                          fontWeight: 600,
                          textTransform: "uppercase",
                          fontSize: 11,
                          letterSpacing: "0.06em",
                        }}
                      >
                        {s.status}
                        {s.latency_ms !== null && (
                          <div
                            style={{
                              fontWeight: 400,
                              fontSize: 11,
                              color: "var(--text-dim)",
                            }}
                          >
                            {s.latency_ms} ms
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                  Немає даних — джерела не сконфігуровано.
                </div>
              )}
            </div>

            <div className="card" style={{ padding: 18 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>
                Найповільніші пошуки · 24h
              </div>
              {quality.slowest_searches.length === 0 ? (
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                  За останні 24 години повільних пошуків не було.
                </div>
              ) : (
                <BarList
                  items={quality.slowest_searches.map((s) => ({
                    label: `${s.niche} · ${s.region}`,
                    value: s.duration_seconds,
                    hint: `${s.leads_count} лідів · ${s.status} · user ${s.user_id ?? "—"}`,
                  }))}
                  formatValue={(n) => `${n.toFixed(1)} с`}
                />
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}

function statusColor(s: string): string {
  if (s === "ok") return "#16A34A";
  if (s === "rate_limited") return "#EAB308";
  if (s === "unconfigured") return "var(--text-dim)";
  return "#EF4444";
}

function Tile({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: number | string;
  hint?: string;
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
          fontSize: 24,
          fontWeight: 700,
          letterSpacing: "-0.02em",
          color: accent ?? "var(--text)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
      {hint && (
        <div
          style={{
            fontSize: 11,
            color: "var(--text-dim)",
            marginTop: 4,
          }}
        >
          {hint}
        </div>
      )}
    </div>
  );
}

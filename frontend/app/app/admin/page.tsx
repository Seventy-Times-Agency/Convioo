"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { BarList } from "@/components/app/MiniChart";
import {
  ApiError,
  getAdminOverview,
  getAdminQuality,
  getAdminSourcesHealth,
  getAdminEnvHealth,
  type AdminOverview,
  type AdminQuality,
  type SourceHealthEntry,
  type EnvHealthItem,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";
import { useIsMobile } from "@/lib/hooks/useMediaQuery";

/**
 * Admin quality / ops dashboard. Deliberately NOT a business view —
 * no MRR, no revenue, no user counts. The job is to surface platform
 * health: Anthropic spend, error rate, queue depth, slowest searches,
 * external-source health. Backend gates ``/api/v1/admin/*`` with the
 * ``is_admin`` flag and 404s non-admins so the route appears to
 * not exist for everyone else.
 */
export default function AdminPage() {
  const { t } = useLocale();
  const router = useRouter();
  const isMobile = useIsMobile();
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [quality, setQuality] = useState<AdminQuality | null>(null);
  const [sources, setSources] = useState<SourceHealthEntry[] | null>(null);
  const [envHealth, setEnvHealth] = useState<EnvHealthItem[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getAdminOverview(),
      getAdminQuality(),
      getAdminSourcesHealth(),
      getAdminEnvHealth(),
    ])
      .then(([ov, q, s, env]) => {
        if (cancelled) return;
        setOverview(ov);
        setQuality(q);
        setSources(s.sources);
        setEnvHealth(env);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          router.replace("/app");
          return;
        }
        showError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <>
      <Topbar
        title={t("admin.title")}
        subtitle={t("admin.subtitle")}
      />
      <div className="page" style={{ maxWidth: 1100 }}>
        {!quality && (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {t("common.loading")}
          </div>
        )}

        {overview && (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "repeat(4, 1fr)",
                gap: 12,
                marginBottom: 18,
              }}
            >
              <Tile label={t("admin.tile.usersTotal")} value={overview.users_total} />
              <Tile
                label={t("admin.tile.paidUsers")}
                value={overview.users_paid}
                hint={t("admin.tile.trialingHint", { n: overview.users_trialing })}
              />
              <Tile label={t("admin.tile.teams")} value={overview.teams_total} />
              <Tile
                label={t("admin.tile.searches7d")}
                value={overview.searches_last_7d}
                hint={t("admin.tile.searches7dHint", {
                  running: overview.searches_running,
                  leads: overview.leads_last_7d,
                })}
                accent={overview.failed_searches_last_24h > 0 ? "#EF4444" : undefined}
              />
            </div>

            <div className="card" style={{ padding: 20, marginBottom: 12 }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>{t("admin.today")}</div>
              <div style={{ display: "flex", gap: 32 }}>
                <div>
                  <div style={{ fontSize: 24, fontWeight: 700 }}>{overview.searches_today}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("admin.searches")}</div>
                </div>
                <div>
                  <div style={{ fontSize: 24, fontWeight: 700 }}>{overview.leads_today}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("admin.newLeads")}</div>
                </div>
              </div>
            </div>

            <div className="card" style={{ padding: 20, marginBottom: 12 }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>{t("admin.pipeline")}</div>
              <div style={{ fontSize: 28, fontWeight: 700 }}>
                ${overview.pipeline_value_usd.toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("admin.totalDealValue")}</div>
            </div>

            <div className="card" style={{ padding: 20, marginBottom: 12 }}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>{t("admin.infrastructure")}</div>
              <div style={{ fontSize: 13 }}>
                {t("admin.dbLatency")}: <strong>{overview.db_latency_ms} ms</strong>
              </div>
              <div style={{ marginTop: 8 }}>
                {Object.entries(overview.source_breakdown || {}).map(([src, cnt]) => (
                  <div key={src} style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {src}: {t("admin.leadsCount", { n: cnt.toLocaleString() })}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {quality && (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "repeat(4, 1fr)",
                gap: 12,
                marginBottom: 18,
              }}
            >
              <Tile
                label={t("admin.tile.anthropicSpend")}
                value={`$${quality.anthropic_estimated_spend_usd.toFixed(2)}`}
                hint={t("admin.tile.anthropicHint", {
                  calls: quality.anthropic_calls_total.toLocaleString(),
                  fail: quality.anthropic_calls_failed,
                })}
                accent={quality.anthropic_calls_failed > 0 ? "#EF4444" : undefined}
              />
              <Tile
                label={t("admin.tile.failureRate24h")}
                value={`${(quality.searches_failure_rate_24h * 100).toFixed(1)}%`}
                hint={`${quality.searches_failed_24h} / ${quality.searches_total_24h}`}
                accent={
                  quality.searches_failure_rate_24h > 0.1 ? "#EF4444" : undefined
                }
              />
              <Tile
                label={t("admin.tile.queueDepth")}
                value={`${quality.queue_pending + quality.queue_running}`}
                hint={t("admin.tile.queueHint", {
                  pending: quality.queue_pending,
                  running: quality.queue_running,
                })}
                accent={
                  quality.queue_running > 5 ? "#EAB308" : undefined
                }
              />
              <Tile
                label={t("admin.tile.searches24h")}
                value={quality.searches_total_24h}
              />
            </div>

            <div className="card" style={{ padding: 18, marginBottom: 12 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>
                {t("admin.sourceHealth")}
              </div>
              {sources && sources.length > 0 ? (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: isMobile ? "1fr" : "repeat(2, 1fr)",
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
                  {t("admin.sourceHealthEmpty")}
                </div>
              )}
            </div>

            <div className="card" style={{ padding: 18 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>
                {t("admin.slowestSearches")}
              </div>
              {quality.slowest_searches.length === 0 ? (
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                  {t("admin.slowestSearchesEmpty")}
                </div>
              ) : (
                <BarList
                  items={quality.slowest_searches.map((s) => ({
                    label: `${s.niche} · ${s.region}`,
                    value: s.duration_seconds,
                    hint: t("admin.slowestSearchHint", {
                      leads: s.leads_count,
                      status: s.status,
                      user: s.user_id ?? t("common.none"),
                    }),
                  }))}
                  formatValue={(n) => t("admin.seconds", { n: n.toFixed(1) })}
                />
              )}
            </div>
          </>
        )}

        <div className="card" style={{ padding: 18, marginTop: 12 }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            {t("admin.apiKeys")}
          </div>
          {!envHealth ? (
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              {t("common.loading")}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {envHealth.map((item) => (
                <div
                  key={item.key}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 10,
                    padding: "7px 10px",
                    borderRadius: 6,
                    border: "1px solid var(--border)",
                    fontSize: 13,
                  }}
                >
                  <span
                    style={{
                      marginTop: 3,
                      flexShrink: 0,
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: item.configured ? "#16A34A" : "#EF4444",
                      display: "inline-block",
                    }}
                  />
                  <div>
                    <div style={{ fontFamily: "monospace", fontWeight: 600 }}>
                      {item.key}
                    </div>
                    {item.note && (
                      <div
                        style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}
                      >
                        {item.note}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
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

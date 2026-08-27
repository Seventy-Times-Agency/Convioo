"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import {
  type DeliverabilityStatus,
  getDeliverabilityStatus,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";

/**
 * Wave 2 — Deliverability settings.
 *
 * Two cards:
 *  1. Warmup / daily sending — progress of today's volume against the
 *     warmup cap, plus the current warmup day and remaining quota.
 *  2. Domain authentication — SPF + DMARC rows with present/absent
 *     indicators and one-line setup hints when a record is missing.
 */

function AuthRow({
  label,
  present,
  detail,
  hint,
}: {
  label: string;
  present: boolean;
  detail?: string | null;
  hint: string;
}) {
  const color = present ? "var(--hot)" : "var(--warm)";
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
        padding: "12px 0",
        borderTop: "1px solid var(--border)",
      }}
    >
      <span
        aria-hidden
        style={{
          flexShrink: 0,
          marginTop: 1,
          color,
          display: "inline-flex",
        }}
      >
        {present ? (
          <Icon name="check" size={16} />
        ) : (
          <span style={{ fontWeight: 700, fontSize: 16, lineHeight: 1 }}>!</span>
        )}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600 }}>{label}</div>
        {present && detail ? (
          <div
            style={{
              fontSize: 12.5,
              color: "var(--text-muted)",
              marginTop: 2,
            }}
          >
            {detail}
          </div>
        ) : null}
        {!present && (
          <div
            style={{
              fontSize: 12.5,
              color: "var(--text-muted)",
              marginTop: 2,
              lineHeight: 1.5,
            }}
          >
            {hint}
          </div>
        )}
      </div>
    </div>
  );
}

export function DeliverabilitySection() {
  const { t } = useLocale();
  const [status, setStatus] = useState<DeliverabilityStatus | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getDeliverabilityStatus()
      .then((s) => {
        if (!cancelled) {
          setStatus(s);
          setError(false);
        }
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const cap = status && status.daily_cap > 0 ? status.daily_cap : 0;
  const sent = status?.sent_today ?? 0;
  const pct =
    cap > 0 ? Math.min(100, Math.round((sent / cap) * 100)) : 0;

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.deliverability.eyebrow")}
      </div>

      {loading ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {t("common.loading")}
        </div>
      ) : error || !status ? (
        <div style={{ fontSize: 13, color: "var(--cold)" }}>
          {t("settings.deliverability.error")}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          {/* ---- Warmup / daily sending ---- */}
          <div>
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                marginBottom: 4,
              }}
            >
              {t("settings.deliverability.warmup.title")}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
                marginBottom: 12,
              }}
            >
              {t("settings.deliverability.warmup.explain")}
            </div>

            {!status.connected && (
              <div
                style={{
                  padding: 12,
                  borderRadius: 10,
                  marginBottom: 12,
                  background:
                    "color-mix(in srgb, var(--warm) 8%, transparent)",
                  border:
                    "1px solid color-mix(in srgb, var(--warm) 25%, var(--border))",
                  fontSize: 13,
                  lineHeight: 1.5,
                  color: "var(--text-muted)",
                }}
              >
                {t("settings.deliverability.notConnected")}{" "}
                <a
                  href="/app/settings/integrations"
                  style={{ color: "var(--accent)" }}
                >
                  {t("settings.deliverability.connectLink")}
                </a>
                .
              </div>
            )}

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                fontSize: 12.5,
                color: "var(--text-muted)",
                marginBottom: 6,
              }}
            >
              <span>
                {t("settings.deliverability.warmup.day", {
                  day: status.warmup_day,
                })}
              </span>
              <span>
                {t("settings.deliverability.warmup.sentOfCap", {
                  sent,
                  cap: status.daily_cap,
                })}
              </span>
            </div>

            <div
              style={{
                height: 8,
                borderRadius: 999,
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${pct}%`,
                  background: "var(--accent)",
                  borderRadius: 999,
                  transition: "width 0.3s ease",
                }}
              />
            </div>

            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                marginTop: 6,
              }}
            >
              {t("settings.deliverability.warmup.remaining", {
                remaining: status.remaining,
              })}
            </div>
          </div>

          {/* ---- Domain authentication ---- */}
          <div>
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                marginBottom: 4,
                display: "flex",
                alignItems: "center",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              {t("settings.deliverability.auth.title")}
              {status.domain && (
                <span
                  className="chip"
                  style={{ fontSize: 11, fontWeight: 500 }}
                >
                  {status.domain}
                </span>
              )}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
                marginBottom: 4,
              }}
            >
              {t("settings.deliverability.auth.explain")}
            </div>

            <AuthRow
              label={t("settings.deliverability.spf.label")}
              present={status.spf.present}
              detail={status.spf.record}
              hint={t("settings.deliverability.spf.hint")}
            />
            <AuthRow
              label={t("settings.deliverability.dmarc.label")}
              present={status.dmarc.present}
              detail={
                status.dmarc.policy
                  ? t("settings.deliverability.dmarc.policy", {
                      policy: status.dmarc.policy,
                    })
                  : null
              }
              hint={t("settings.deliverability.dmarc.hint")}
            />
          </div>
        </div>
      )}
    </div>
  );
}

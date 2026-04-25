"use client";

import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { useLocale } from "@/lib/i18n";

interface HealthSummary {
  status: string;
  db: boolean;
  commit: string;
}

export default function SettingsPage() {
  const { t } = useLocale();
  const [health, setHealth] = useState<HealthSummary | null>(null);
  const [queueEnabled, setQueueEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "";
    if (!base) return;
    const root = base.replace(/\/$/, "");
    fetch(`${root}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
    fetch(`${root}/api/v1/queue/status`)
      .then((r) => r.json())
      .then((b) => setQueueEnabled(b.queue_enabled))
      .catch(() => setQueueEnabled(null));
  }, []);

  const integrations: Array<{
    name: string;
    status: "connected" | "pending";
    detail?: string;
  }> = [
    {
      name: t("settings.int.googlePlaces"),
      status: "connected",
      detail: "GOOGLE_PLACES_API_KEY",
    },
    {
      name: t("settings.int.anthropic"),
      status: "connected",
      detail: "ANTHROPIC_API_KEY",
    },
    {
      name: t("settings.int.telegram"),
      status: "connected",
      detail: "BOT_TOKEN",
    },
    {
      name: t("settings.int.redis"),
      status: queueEnabled ? "connected" : "pending",
      detail: queueEnabled
        ? t("settings.int.redis.connected")
        : t("settings.int.redis.fallback"),
    },
    {
      name: t("settings.int.email"),
      status: "pending",
      detail: t("settings.int.email.planned"),
    },
  ];

  return (
    <>
      <Topbar title={t("settings.title")} subtitle={t("settings.subtitle")} />
      <div className="page" style={{ maxWidth: 720 }}>
        <div className="card" style={{ padding: 24, marginBottom: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("settings.workspace")}
          </div>
          <KV label={t("settings.workspaceName")} value="Convioo" />
          <div style={{ marginTop: 16 }}>
            <KV label={t("settings.auth")} value={t("settings.authValue")} />
          </div>
        </div>

        <div className="card" style={{ padding: 24, marginBottom: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("settings.backend")}
          </div>
          <KV
            label={t("settings.health")}
            value={
              health
                ? `${health.status} · db=${health.db ? "ok" : "down"}`
                : t("settings.unknown")
            }
          />
          <div style={{ marginTop: 16 }}>
            <KV
              label={t("settings.commit")}
              value={health?.commit ?? t("settings.unknown")}
              mono
            />
          </div>
        </div>

        <div className="card" style={{ padding: 24 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("settings.integrations")}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {integrations.map((i, k) => (
              <div
                key={i.name}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "10px 0",
                  borderBottom:
                    k < integrations.length - 1
                      ? "1px solid var(--border)"
                      : "none",
                }}
              >
                <div>
                  <div style={{ fontSize: 14 }}>{i.name}</div>
                  {i.detail && (
                    <div style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
                      {i.detail}
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span
                    className="status-dot"
                    style={{
                      background:
                        i.status === "connected"
                          ? "var(--hot)"
                          : "var(--text-dim)",
                    }}
                  />
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {i.status === "connected"
                      ? t("settings.int.connected")
                      : t("settings.int.notConfigured")}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card" style={{ padding: 24, marginTop: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("settings.connectors")}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {(
              [
                {
                  key: "gmail",
                  icon: "mail" as const,
                  name: t("settings.connector.gmail"),
                  desc: t("settings.connector.gmail.desc"),
                },
                {
                  key: "outlook",
                  icon: "mail" as const,
                  name: t("settings.connector.outlook"),
                  desc: t("settings.connector.outlook.desc"),
                },
                {
                  key: "smtp",
                  icon: "send" as const,
                  name: t("settings.connector.smtp"),
                  desc: t("settings.connector.smtp.desc"),
                },
              ]
            ).map((c) => (
              <div
                key={c.key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 14px",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  background: "var(--surface-2)",
                  opacity: 0.85,
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    display: "grid",
                    placeItems: "center",
                    color: "var(--text-muted)",
                    flexShrink: 0,
                  }}
                >
                  <Icon name={c.icon} size={15} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{c.name}</div>
                  <div
                    style={{
                      fontSize: 11.5,
                      color: "var(--text-dim)",
                      marginTop: 2,
                      lineHeight: 1.45,
                    }}
                  >
                    {c.desc}
                  </div>
                </div>
                <span
                  className="chip"
                  style={{
                    fontSize: 10,
                    color: "var(--text-dim)",
                    flexShrink: 0,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                  }}
                >
                  {t("settings.connector.soon")}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled
                  style={{ flexShrink: 0 }}
                >
                  {t("settings.connector.connect")}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function KV({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        {label}
      </div>
      <div
        style={{
          fontSize: 14,
          fontFamily: mono ? "var(--font-mono)" : undefined,
        }}
      >
        {value}
      </div>
    </div>
  );
}

"use client";

import { useLocale } from "@/lib/i18n";

export function SlackSection() {
  const { t } = useLocale();
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.slack.eyebrow")}
      </div>
      <p
        style={{
          fontSize: 13,
          color: "var(--text-muted)",
          marginBottom: 12,
        }}
      >
        {t("settings.slack.notifyDesc", { op: ">=", score: 80, status: "won" })}
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        {t("settings.slack.webhookHelp")}
      </div>
    </div>
  );
}
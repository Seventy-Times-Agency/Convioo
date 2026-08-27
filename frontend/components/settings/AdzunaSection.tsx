"use client";

import { useLocale } from "@/lib/i18n";

export function AdzunaSection() {
  const { t } = useLocale();
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.adzuna.title")}
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        {t("settings.adzuna.body")}
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        {t("settings.adzuna.envIntro")}{" "}
        <code>ADZUNA_APP_ID</code> {t("settings.adzuna.and")} <code>ADZUNA_API_KEY</code>.
        {" "}{t("settings.adzuna.enableFlag")} <code>ADZUNA_ENABLED=true</code>.
      </div>
    </div>
  );
}

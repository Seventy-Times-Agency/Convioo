"use client";

import { useLocale } from "@/lib/i18n";

export function HunterSection() {
  const { t } = useLocale();
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.hunter.title")}
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        {t("settings.hunter.body")}
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        {t("settings.hunter.envIntro")}{" "}
        <code>HUNTER_API_KEY</code>.
        {" "}{t("settings.hunter.noKey")}
      </div>
    </div>
  );
}

"use client";

import { useLocale } from "@/lib/i18n";

export function CompaniesHouseSection() {
  const { t } = useLocale();
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.companiesHouse.title")}
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        {t("settings.companiesHouse.body")}
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        {t("settings.companiesHouse.envIntro")}{" "}
        <code>COMPANIES_HOUSE_ENABLED=true</code>.
        {" "}{t("settings.companiesHouse.noKey")}
      </div>
    </div>
  );
}

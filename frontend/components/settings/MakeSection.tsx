"use client";

import { useLocale } from "@/lib/i18n";

export function MakeSection() {
  const { t } = useLocale();
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14, opacity: 0.7 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: 14,
        }}
      >
        <div className="eyebrow">Make.com (ex-Integromat)</div>
        <div
          className="chip"
          style={{ fontSize: 10, padding: "2px 7px", marginLeft: "auto" }}
        >
          {t("billing.cta")}
        </div>
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        {t("settings.make.intro")}
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        {t("settings.make.helpBefore")}{" "}
        <a href="/developers" style={{ color: "var(--accent)" }}>
          {t("nav.developers")}
        </a>{" "}
        {t("settings.make.helpAfter")}
      </div>
    </div>
  );
}

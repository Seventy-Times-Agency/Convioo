"use client";

import { useState } from "react";
import { useLocale } from "@/lib/i18n";

export function MobileBanner() {
  const { t } = useLocale();
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  return (
    <div
      className="mobile-only-banner"
      style={{
        display: "none",
        background: "var(--surface-2)",
        borderBottom: "1px solid var(--border)",
        padding: "10px 16px",
        fontSize: 13,
        color: "var(--text-muted)",
        alignItems: "center",
        gap: 10,
      }}
    >
      <span style={{ flex: 1 }}>
        {t("mobile.banner")}
      </span>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          fontSize: 16,
          color: "var(--text-dim)",
          padding: "0 4px",
          lineHeight: 1,
        }}
        aria-label={t("common.close")}
      >
        ×
      </button>
    </div>
  );
}

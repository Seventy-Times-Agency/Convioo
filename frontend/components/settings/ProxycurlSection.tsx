"use client";

import { useLocale } from "@/lib/i18n";

export function ProxycurlSection() {
  const { t } = useLocale();
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        ProxyCurl (LinkedIn LPR)
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        {t("settings.proxycurl.body")}
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        {t("settings.proxycurl.envIntro")}{" "}
        <code>PROXYCURL_API_KEY</code>.
      </div>
    </div>
  );
}

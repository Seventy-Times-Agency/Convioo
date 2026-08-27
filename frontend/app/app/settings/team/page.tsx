"use client";

import Link from "next/link";

import { useLocale } from "@/lib/i18n";

export default function SettingsTeamPage() {
  const { t } = useLocale();
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.team.eyebrow")}
      </div>
      <div
        style={{
          fontSize: 13.5,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 14,
        }}
      >
        {t("settings.team.body")}
      </div>
      <Link href="/app/team" className="btn btn-sm">
        {t("settings.team.open")}
      </Link>
    </div>
  );
}

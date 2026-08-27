"use client";

import { ReplayTourButton } from "@/components/app/OnboardingTour";
import { useLocale } from "@/lib/i18n";

export function HelpSection() {
  const { t } = useLocale();
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.help.title")}
      </div>
      <div
        style={{
          fontSize: 13.5,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 12,
        }}
      >
        {t("settings.help.body")}
      </div>
      <ReplayTourButton className="btn btn-ghost btn-sm">
        {t("settings.help.replayTour")}
      </ReplayTourButton>
    </div>
  );
}

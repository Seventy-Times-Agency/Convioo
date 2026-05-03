"use client";

import { ReplayTourButton } from "@/components/app/OnboardingTour";

export function HelpSection() {
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Помощь
      </div>
      <div
        style={{
          fontSize: 13.5,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 12,
        }}
      >
        Запустите 4-шаговый тур заново, если хочется ещё раз пройтись
        по основным экранам.
      </div>
      <ReplayTourButton className="btn btn-ghost btn-sm">
        Пройти тур заново
      </ReplayTourButton>
    </div>
  );
}

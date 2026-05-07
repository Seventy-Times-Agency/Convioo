"use client";

export function AdzunaSection() {
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Adzuna — Job Postings
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        Находит компании, которые активно нанимают в вашей нише прямо сейчас.
        Например: «Ищут SMM-специалиста (3 дня назад)» — сигнал о росте, горячий момент
        для холодного контакта. Покрытие: UK, US, AU, CA, DE, FR.
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        Ключи сохраняются через Railway env переменные{" "}
        <code>ADZUNA_APP_ID</code> и <code>ADZUNA_API_KEY</code>.
        После добавления активируйте флаг <code>ADZUNA_ENABLED=true</code>.
      </div>
    </div>
  );
}

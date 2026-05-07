"use client";

export function CompaniesHouseSection() {
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Companies House / SAM.gov — Новые бизнесы
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        Находит компании, зарегистрированные менее 6 месяцев назад. Новые бизнесы
        часто не имеют подрядчиков и активно ищут агентства — идеальный момент для
        первого контакта. Покрытие: UK (Companies House) и US (SAM.gov).
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        Бесплатный источник. Включается флагом Railway env переменной{" "}
        <code>COMPANIES_HOUSE_ENABLED=true</code>.
        Для Companies House API-ключ не нужен.
      </div>
    </div>
  );
}

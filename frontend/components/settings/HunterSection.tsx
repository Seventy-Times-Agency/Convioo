"use client";

export function HunterSection() {
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Hunter.io — Email Finder
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        Если email не найден на сайте компании, система автоматически запрашивает
        Hunter.io по домену. Бесплатный план: 25 запросов/месяц.
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        API ключ сохраняется через Railway env переменную{" "}
        <code>HUNTER_API_KEY</code>.
        Без ключа используются только email-адреса с сайта компании.
      </div>
    </div>
  );
}

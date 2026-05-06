"use client";

export function MakeSection() {
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
          Скоро
        </div>
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        Нативные модули Make.com для запуска поиска, получения лидов и отправки
        email прямо из ваших сценариев автоматизации. Аналог уже готового
        Zapier-приложения.
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        Используйте публичный API + API-ключ из раздела{" "}
        <a href="/developers" style={{ color: "var(--accent)" }}>
          Разработчикам
        </a>{" "}
        уже сейчас, пока нативные модули в разработке.
      </div>
    </div>
  );
}

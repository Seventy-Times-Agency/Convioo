"use client";

export function ProxycurlSection() {
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        ProxyCurl (LinkedIn LPR)
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        Опциональный поиск лица принимающего решение через LinkedIn.
        Стоимость ~$0.01 за запрос. Без ключа используются бесплатные источники:
        парсинг сайта и OpenCorporates.
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        API ключ сохраняется через Railway env переменную{" "}
        <code>PROXYCURL_API_KEY</code>.
      </div>
    </div>
  );
}

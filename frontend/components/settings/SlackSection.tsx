"use client";

export function SlackSection() {
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Slack уведомления
      </div>
      <p
        style={{
          fontSize: 13,
          color: "var(--text-muted)",
          marginBottom: 12,
        }}
      >
        Получайте уведомления когда находится горячий лид (score {">="} 80) или
        сделка переходит в статус &quot;won&quot;.
      </p>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
        Webhook URL сохраняется через Railway env переменную
        SLACK_WEBHOOK_URL.
      </div>
    </div>
  );
}
"use client";

import { useState } from "react";
import { showInfo } from "@/lib/toast";

export function SlackSection() {
  const [webhookUrl, setWebhookUrl] = useState("");

  const handleSave = () => {
    showInfo(
      "Webhook URL сохраняется через Railway env переменную SLACK_WEBHOOK_URL"
    );
  };

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
        Получайте уведомления когда находится горячий лид (score >= 80) или
        сделка переходит в статус "won".
      </p>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          placeholder="https://hooks.slack.com/services/..."
          style={{ flex: 1 }}
          value={webhookUrl}
          onChange={(e) => setWebhookUrl(e.target.value)}
        />
        <button
          className="btn btn-sm"
          type="button"
          onClick={handleSave}
        >
          Сохранить
        </button>
      </div>
      <div
        style={{
          fontSize: 12,
          color: "var(--text-dim)",
          marginTop: 8,
        }}
      >
        Webhook URL из настроек вашего Slack workspace
      </div>
    </div>
  );
}

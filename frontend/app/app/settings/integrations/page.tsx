"use client";

import { useState } from "react";
import { NotionSection } from "@/components/settings/NotionSection";
import { HubspotSection } from "@/components/settings/HubspotSection";
import { PipedriveSection } from "@/components/settings/PipedriveSection";
import { GmailSection } from "@/components/settings/GmailSection";
import { OutlookSection } from "@/components/settings/OutlookSection";
import { BackendInfoCards } from "@/components/settings/BackendInfoCards";
import { showInfo } from "@/lib/toast";

export default function SettingsIntegrationsPage() {
  const [webhookUrl, setWebhookUrl] = useState("");

  const handleSlackSave = () => {
    showInfo(
      "Webhook URL сохраняется через Railway env переменную SLACK_WEBHOOK_URL"
    );
  };

  return (
    <>
      <GmailSection />
      <OutlookSection />
      <NotionSection />
      <HubspotSection />
      <PipedriveSection />
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
            onClick={handleSlackSave}
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
      <BackendInfoCards />
    </>
  );
}

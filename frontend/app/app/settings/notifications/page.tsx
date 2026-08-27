"use client";

import { useEffect, useState } from "react";
import {
  getNotificationPrefs,
  updateNotificationPrefs,
  type NotificationPrefs,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";

export default function SettingsNotificationsPage() {
  const { t } = useLocale();
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    void getNotificationPrefs()
      .then(setPrefs)
      .catch((e) =>
        showError(e instanceof Error ? e.message : String(e)),
      );
  }, []);

  const toggle = async (
    key: "dailyDigestEnabled" | "emailReplyTrackingEnabled",
    value: boolean,
  ) => {
    setBusy(true);
    setInfo(null);
    try {
      const updated = await updateNotificationPrefs({ [key]: value });
      setPrefs(updated);
      setInfo(t("common.saved"));
      setTimeout(() => setInfo(null), 1500);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.notifications.eyebrow")}
      </div>
      <div
        style={{
          fontSize: 13,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 18,
        }}
      >
        {t("settings.notifications.intro")}
      </div>

      {prefs === null && (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {t("common.loading")}
        </div>
      )}

      {prefs && (
        <>
          <ToggleRow
            title={t("settings.notifications.digest.title")}
            description={t("settings.notifications.digest.desc")}
            checked={prefs.daily_digest_enabled}
            disabled={busy}
            onChange={(v) => void toggle("dailyDigestEnabled", v)}
          />
          <ToggleRow
            title={t("settings.notifications.replyTracking.title")}
            description={t("settings.notifications.replyTracking.desc")}
            checked={prefs.email_reply_tracking_enabled}
            disabled={busy}
            onChange={(v) => void toggle("emailReplyTrackingEnabled", v)}
            footer={
              prefs.email_reply_last_checked_at
                ? t("settings.notifications.replyTracking.lastChecked", {
                    when: new Date(
                      prefs.email_reply_last_checked_at,
                    ).toLocaleString(),
                  })
                : t("settings.notifications.replyTracking.neverChecked")
            }
          />
        </>
      )}

      {info && (
        <div
          style={{
            fontSize: 12.5,
            color: "var(--accent)",
            marginTop: 10,
          }}
        >
          {info}
        </div>
      )}
    </div>
  );
}

function ToggleRow({
  title,
  description,
  checked,
  disabled,
  onChange,
  footer,
}: {
  title: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onChange: (next: boolean) => void;
  footer?: string;
}) {
  const { t } = useLocale();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 14,
        padding: "14px 0",
        borderTop: "1px solid var(--border)",
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 4 }}>
          {title}
        </div>
        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-muted)",
            lineHeight: 1.5,
          }}
        >
          {description}
        </div>
        {footer && (
          <div
            style={{
              fontSize: 11.5,
              color: "var(--text-dim)",
              marginTop: 6,
            }}
          >
            {footer}
          </div>
        )}
      </div>
      <label
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.6 : 1,
          userSelect: "none",
        }}
      >
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          style={{
            width: 18,
            height: 18,
            cursor: disabled ? "not-allowed" : "pointer",
          }}
        />
        <span style={{ fontSize: 13 }}>
          {checked ? t("common.on") : t("common.off")}
        </span>
      </label>
    </div>
  );
}

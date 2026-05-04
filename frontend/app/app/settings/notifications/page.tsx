"use client";

import { useEffect, useState } from "react";
import {
  getNotificationPrefs,
  updateNotificationPrefs,
  type NotificationPrefs,
} from "@/lib/api";

export default function SettingsNotificationsPage() {
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    void getNotificationPrefs()
      .then(setPrefs)
      .catch((e) =>
        setError(e instanceof Error ? e.message : String(e)),
      );
  }, []);

  const toggle = async (
    key: "dailyDigestEnabled" | "emailReplyTrackingEnabled",
    value: boolean,
  ) => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const updated = await updateNotificationPrefs({ [key]: value });
      setPrefs(updated);
      setInfo("Сохранено.");
      setTimeout(() => setInfo(null), 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Уведомления
      </div>
      <div
        style={{
          fontSize: 13,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 18,
        }}
      >
        Транзакционные письма (верификация email, восстановление пароля,
        вход с нового устройства) приходят автоматически. Опциональные
        дайджесты и трекинг ответов — управляются ниже.
      </div>

      {prefs === null && !error && (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          Загрузка…
        </div>
      )}

      {prefs && (
        <>
          <ToggleRow
            title="Ежедневный дайджест"
            description="Раз в сутки присылаем сводку: новые лиды, hot-лиды (score ≥ 75), ответы на исходящие письма. Не присылаем, если за сутки ничего не произошло."
            checked={prefs.daily_digest_enabled}
            disabled={busy}
            onChange={(v) => void toggle("dailyDigestEnabled", v)}
          />
          <ToggleRow
            title="Отслеживание ответов в Gmail"
            description="Каждые несколько минут проверяем входящие на ответы по письмам, которые ты отправил из CRM. Найденный ответ записывается в активность лида и автоматом меняет статус new/contacted → replied."
            checked={prefs.email_reply_tracking_enabled}
            disabled={busy}
            onChange={(v) => void toggle("emailReplyTrackingEnabled", v)}
            footer={
              prefs.email_reply_last_checked_at
                ? `Последняя проверка: ${new Date(prefs.email_reply_last_checked_at).toLocaleString()}`
                : "Ещё ни разу не проверялось."
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
      {error && (
        <div
          style={{
            fontSize: 12.5,
            color: "var(--cold)",
            marginTop: 10,
          }}
        >
          {error}
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
        <span style={{ fontSize: 13 }}>{checked ? "Вкл" : "Выкл"}</span>
      </label>
    </div>
  );
}

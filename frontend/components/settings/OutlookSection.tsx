"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  disconnectOutlook,
  getOutlookStatus,
  startOutlookAuthorize,
  type OutlookIntegrationStatus,
} from "@/lib/api";

export function OutlookSection() {
  const [status, setStatus] = useState<OutlookIntegrationStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getOutlookStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled)
          setStatus({
            connected: false,
            account_email: null,
            scope: null,
            expires_at: null,
          });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await startOutlookAuthorize();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm("Отключить Outlook? Сохранённые токены будут удалены."))
      return;
    setBusy(true);
    setError(null);
    try {
      await disconnectOutlook();
      setStatus({
        connected: false,
        account_email: null,
        scope: null,
        expires_at: null,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Интеграция: Microsoft 365 (Outlook)
      </div>

      {status === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          Загрузка…
        </div>
      ) : status.connected ? (
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 16,
            justifyContent: "space-between",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Подключено как {status.account_email ?? "—"}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              Доступ ограничен скоупом Mail.Send + Mail.Read — мы можем
              отправлять письма и отслеживать ответы, но не читать почту.
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void disconnect()}
            disabled={busy}
            style={{ color: "var(--cold)" }}
          >
            Отключить
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            Подключите Microsoft 365 чтобы отправлять холодные письма прямо из
            карточки лида. Работает с корпоративными аккаунтами и личными
            аккаунтами Microsoft (@outlook.com, @hotmail.com).
          </p>
          <div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void connect()}
              disabled={busy}
            >
              {busy ? "..." : "Подключить Outlook"}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: 12,
            fontSize: 12.5,
            color: "var(--cold)",
            lineHeight: 1.5,
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  disconnectHubspot,
  getHubspotStatus,
  startHubspotAuthorize,
  type HubspotIntegrationStatus,
} from "@/lib/api";

export function HubspotSection() {
  const [status, setStatus] = useState<HubspotIntegrationStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getHubspotStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled)
          setStatus({
            connected: false,
            portal_id: null,
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
      const { url } = await startHubspotAuthorize();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm("Отключить HubSpot? Сохранённые токены будут удалены.")) return;
    setBusy(true);
    setError(null);
    try {
      await disconnectHubspot();
      setStatus({
        connected: false,
        portal_id: null,
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
        Интеграция: HubSpot
      </div>

      {status === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
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
              Подключено
              {status.account_email ? ` (${status.account_email})` : ""}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              Portal ID:{" "}
              <span style={{ fontFamily: "var(--font-mono)" }}>
                {status.portal_id ?? "—"}
              </span>
              <br />
              Скоупы: contacts.write + contacts.read.
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
            Подключите HubSpot чтобы экспортировать выбранных лидов
            прямо в ваш CRM-портал. Конвиу пишет только в Contacts —
            никаких изменений в сделках, компаниях или заметках.
          </p>
          <div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void connect()}
              disabled={busy}
            >
              {busy ? "..." : "Подключить HubSpot"}
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

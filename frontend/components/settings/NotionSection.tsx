"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  connectNotion,
  disconnectNotion,
  getNotionStatus,
  type NotionIntegrationStatus,
} from "@/lib/api";

export function NotionSection() {
  const [status, setStatus] = useState<NotionIntegrationStatus | null>(null);
  const [editing, setEditing] = useState(false);
  const [token, setToken] = useState("");
  const [databaseId, setDatabaseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getNotionStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled) setStatus({
          connected: false,
          token_preview: null,
          database_id: null,
          workspace_name: null,
          updated_at: null,
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!token.trim() || !databaseId.trim()) return;
    setBusy(true);
    try {
      const next = await connectNotion({
        token: token.trim(),
        databaseId: databaseId.trim(),
      });
      setStatus(next);
      setEditing(false);
      setToken("");
      setDatabaseId("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm("Отключить Notion? Сохранённый токен будет удалён.")) return;
    setBusy(true);
    setError(null);
    try {
      await disconnectNotion();
      setStatus({
        connected: false,
        token_preview: null,
        database_id: null,
        workspace_name: null,
        updated_at: null,
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
        Интеграция: Notion
      </div>

      {status === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
      ) : status.connected && !editing ? (
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
              {status.workspace_name ?? "Notion подключён"}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
              Токен:{" "}
              <span style={{ fontFamily: "var(--font-mono)" }}>
                {status.token_preview ?? "—"}
              </span>
              <br />
              Database ID:{" "}
              <span style={{ fontFamily: "var(--font-mono)" }}>
                {status.database_id ?? "—"}
              </span>
            </div>
            <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 6 }}>
              Лиды экспортируются как страницы в эту базу. Колонки
              мапятся по имени (Name → Title, Score → Number и т.д.).
            </div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setEditing(true)}
              disabled={busy}
            >
              Сменить
            </button>
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
        </div>
      ) : (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5, margin: 0 }}>
            1. Создайте интеграцию на{" "}
            <a
              href="https://www.notion.so/my-integrations"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--accent)" }}
            >
              notion.so/my-integrations
            </a>
            , скопируйте Internal Integration Token.
            <br />
            2. Откройте базу-приёмник в Notion → Share → пригласите эту интеграцию.
            <br />
            3. Скопируйте Database ID из URL базы (32-значный hex).
          </p>
          <input
            className="input"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="ntn_•••••••••••••"
            autoComplete="off"
          />
          <input
            className="input"
            value={databaseId}
            onChange={(e) => setDatabaseId(e.target.value)}
            placeholder="Database ID (32 hex)"
          />
          {error && <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="submit"
              className="btn btn-sm"
              disabled={busy || !token.trim() || !databaseId.trim()}
            >
              {busy ? "Проверяю доступ…" : "Подключить"}
            </button>
            {status?.connected && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setEditing(false)}
                disabled={busy}
              >
                Отмена
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

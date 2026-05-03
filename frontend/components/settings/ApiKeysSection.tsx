"use client";

import { useEffect, useState } from "react";
import {
  createApiKey,
  listMyApiKeys,
  revokeApiKey,
  type ApiKey,
  type ApiKeyCreated,
} from "@/lib/api";

export function ApiKeysSection() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draftLabel, setDraftLabel] = useState("");
  const [justCreated, setJustCreated] = useState<ApiKeyCreated | null>(null);

  const refresh = async () => {
    try {
      const r = await listMyApiKeys();
      setKeys(r.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await createApiKey(draftLabel.trim() || null);
      setJustCreated(created);
      setDraftLabel("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string) => {
    if (!confirm("Отозвать ключ? Любые скрипты, использующие его, перестанут работать.")) return;
    setBusy(true);
    try {
      await revokeApiKey(id);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        API-ключи
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: "var(--text-muted)",
          lineHeight: 1.5,
          marginBottom: 12,
        }}
      >
        Используй для скриптов / Zapier / Make. Передавай как заголовок{" "}
        <code style={{ fontFamily: "var(--font-mono)" }}>Authorization: Bearer convioo_pk_…</code>.
        Каждый ключ работает от имени этого аккаунта.
      </div>

      {justCreated && (
        <div
          style={{
            border: "1px solid var(--accent)",
            background: "var(--accent-soft)",
            borderRadius: 10,
            padding: 12,
            marginBottom: 12,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
            Скопируйте сейчас — повторно показать не сможем:
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <code
              style={{
                flex: 1,
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                padding: "6px 8px",
                background: "var(--surface)",
                borderRadius: 6,
                wordBreak: "break-all",
              }}
            >
              {justCreated.token}
            </code>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                void navigator.clipboard?.writeText(justCreated.token);
              }}
            >
              Скопировать
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setJustCreated(null)}
            >
              ОК
            </button>
          </div>
        </div>
      )}

      <form onSubmit={create} style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        <input
          className="input"
          value={draftLabel}
          onChange={(e) => setDraftLabel(e.target.value)}
          placeholder="Название ключа (например, 'Zapier')"
          style={{ flex: 1, fontSize: 13 }}
        />
        <button type="submit" className="btn btn-sm" disabled={busy}>
          {busy ? "..." : "Создать ключ"}
        </button>
      </form>

      {error && <div style={{ fontSize: 13, color: "var(--cold)", marginBottom: 8 }}>{error}</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {keys === null ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
        ) : keys.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Пока ни одного ключа.
          </div>
        ) : (
          keys.map((k) => (
            <div
              key={k.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 10,
                padding: 12,
                display: "flex",
                gap: 12,
                alignItems: "center",
                opacity: k.revoked ? 0.5 : 1,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>
                  {k.label ?? "Без названия"}
                  {k.revoked && (
                    <span
                      style={{
                        marginLeft: 8,
                        fontSize: 10,
                        color: "var(--cold)",
                        textTransform: "uppercase",
                        letterSpacing: 0.5,
                      }}
                    >
                      отозван
                    </span>
                  )}
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                    color: "var(--text-muted)",
                  }}
                >
                  {k.token_preview} · {k.last_used_at ? `последнее использование ${new Date(k.last_used_at).toLocaleDateString()}` : "никогда не использовался"}
                </div>
              </div>
              {!k.revoked && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => void revoke(k.id)}
                  style={{ color: "var(--cold)" }}
                  disabled={busy}
                >
                  Отозвать
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

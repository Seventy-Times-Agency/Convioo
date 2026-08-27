"use client";

import { useEffect, useState } from "react";
import {
  createApiKey,
  listMyApiKeys,
  revokeApiKey,
  type ApiKey,
  type ApiKeyCreated,
} from "@/lib/api";
import { showError } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";
import { useLocale } from "@/lib/i18n";

export function ApiKeysSection() {
  const { t } = useLocale();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [draftLabel, setDraftLabel] = useState("");
  const [justCreated, setJustCreated] = useState<ApiKeyCreated | null>(null);

  const refresh = async () => {
    try {
      const r = await listMyApiKeys();
      setKeys(r.items);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await createApiKey(draftLabel.trim() || null);
      setJustCreated(created);
      setDraftLabel("");
      await refresh();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string) => {
    if (!(await confirmAsync(t("settings.apiKeys.confirmRevoke")))) return;
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
        {t("settings.apiKeys.title")}
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: "var(--text-muted)",
          lineHeight: 1.5,
          marginBottom: 12,
        }}
      >
        {t("settings.apiKeys.descUse")}{" "}
        <code style={{ fontFamily: "var(--font-mono)" }}>Authorization: Bearer convioo_pk_…</code>.
        {" "}{t("settings.apiKeys.descScope")}
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
            {t("settings.apiKeys.copyNow")}
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
              {t("settings.copy")}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setJustCreated(null)}
            >
              {t("settings.ok")}
            </button>
          </div>
        </div>
      )}

      <form onSubmit={create} style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        <input
          className="input"
          value={draftLabel}
          onChange={(e) => setDraftLabel(e.target.value)}
          placeholder={t("settings.apiKeys.labelPlaceholder")}
          style={{ flex: 1, fontSize: 13 }}
        />
        <button type="submit" className="btn btn-sm" disabled={busy}>
          {busy ? "..." : t("settings.apiKeys.create")}
        </button>
      </form>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {keys === null ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("common.loading")}</div>
        ) : keys.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {t("settings.apiKeys.empty")}
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
                  {k.label ?? t("settings.apiKeys.untitled")}
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
                      {t("settings.apiKeys.revoked")}
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
                  {k.token_preview} · {k.last_used_at ? t("settings.apiKeys.lastUsed", { date: new Date(k.last_used_at).toLocaleDateString() }) : t("settings.apiKeys.neverUsed")}
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
                  {t("settings.apiKeys.revoke")}
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

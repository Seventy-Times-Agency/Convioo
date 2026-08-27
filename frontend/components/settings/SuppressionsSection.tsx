"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  addSuppression,
  listSuppressions,
  removeSuppression,
  type Suppression,
} from "@/lib/api";
import { showError, showSuccess } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";
import { useLocale } from "@/lib/i18n";

/**
 * Do-not-contact list manager. Lets a user honour an unsubscribe / "please
 * stop" request by adding the recipient's email here; the backend then
 * blocks every outreach send to it, even if the same address is
 * re-scraped in a later search.
 */
export function SuppressionsSection() {
  const { t } = useLocale();
  const [items, setItems] = useState<Suppression[] | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      setItems(await listSuppressions());
    } catch {
      setItems([]);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = email.trim();
    if (!value) return;
    setBusy(true);
    try {
      await addSuppression(value);
      setEmail("");
      await refresh();
      showSuccess(t("settings.suppressions.added"));
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (value: string) => {
    if (!(await confirmAsync(t("settings.suppressions.removeConfirm")))) return;
    setBusy(true);
    try {
      await removeSuppression(value);
      await refresh();
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        {t("settings.suppressions.eyebrow")}
      </div>
      <p
        style={{
          fontSize: 12.5,
          color: "var(--text-muted)",
          lineHeight: 1.5,
          margin: "0 0 14px",
        }}
      >
        {t("settings.suppressions.desc")}
      </p>

      <form
        onSubmit={submit}
        style={{ display: "flex", gap: 8, marginBottom: 16 }}
      >
        <input
          className="input"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t("settings.suppressions.placeholder")}
          style={{ flex: 1 }}
          autoComplete="off"
        />
        <button
          type="submit"
          className="btn btn-sm"
          disabled={busy || !email.trim()}
        >
          {t("settings.suppressions.add")}
        </button>
      </form>

      {items === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {t("common.loading")}
        </div>
      ) : items.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--text-dim)" }}>
          {t("settings.suppressions.empty")}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {items.map((row) => (
            <div
              key={row.email}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 10,
                padding: "8px 12px",
                border: "1px solid var(--border)",
                borderRadius: 8,
                background: "var(--surface)",
              }}
            >
              <span
                style={{
                  fontSize: 13,
                  fontFamily: "var(--font-mono)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {row.email}
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => void remove(row.email)}
                disabled={busy}
                style={{ color: "var(--cold)", flexShrink: 0 }}
              >
                {t("settings.suppressions.remove")}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { deleteAccount, gdprExportUrl, getMyProfile } from "@/lib/api";
import { clearCurrentUser } from "@/lib/auth";
import { showError } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";
import { useLocale } from "@/lib/i18n";

export function AccountDangerZoneSection() {
  const { t } = useLocale();
  const [email, setEmail] = useState<string | null>(null);
  const [confirmEmail, setConfirmEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [showDelete, setShowDelete] = useState(false);

  useEffect(() => {
    void getMyProfile()
      .then((p) => setEmail(p.email ?? null))
      .catch(() => setEmail(null));
  }, []);

  const downloadExport = () => {
    setInfo(t("settings.danger.preparingArchive"));
    // Same-origin link, cookie auth attaches automatically.
    window.location.href = gdprExportUrl();
  };

  const submitDelete = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email) {
      showError(t("settings.danger.error.noEmail"));
      return;
    }
    if (confirmEmail.trim().toLowerCase() !== email.toLowerCase()) {
      showError(t("settings.danger.error.emailMismatch"));
      return;
    }
    if (!(await confirmAsync(t("settings.danger.confirmDelete")))) return;
    setBusy(true);
    try {
      await deleteAccount({
        confirmEmail: confirmEmail.trim(),
        password: password || undefined,
      });
      clearCurrentUser();
      window.location.href = "/";
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.danger.title")}
      </div>

      <div style={{ marginBottom: 22 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>
          {t("settings.danger.exportTitle")}
        </div>
        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-muted)",
            lineHeight: 1.5,
            marginBottom: 10,
          }}
        >
          {t("settings.danger.exportBody")}
        </div>
        <button
          type="button"
          className="btn btn-sm"
          onClick={downloadExport}
          disabled={busy}
        >
          {t("settings.danger.downloadArchive")}
        </button>
        {info && (
          <div
            style={{
              fontSize: 12.5,
              color: "var(--text-muted)",
              marginTop: 8,
            }}
          >
            {info}
          </div>
        )}
      </div>

      <div
        style={{
          borderTop: "1px solid var(--border)",
          paddingTop: 18,
        }}
      >
        <div
          style={{
            fontSize: 13.5,
            fontWeight: 600,
            marginBottom: 6,
            color: "var(--cold)",
          }}
        >
          {t("settings.danger.deleteTitle")}
        </div>
        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-muted)",
            lineHeight: 1.5,
            marginBottom: 10,
          }}
        >
          {t("settings.danger.deleteBody")}
        </div>

        {!showDelete ? (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            style={{ color: "var(--cold)" }}
            onClick={() => setShowDelete(true)}
          >
            {t("settings.danger.iWantToDelete")}
          </button>
        ) : (
          <form
            onSubmit={submitDelete}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
              maxWidth: 420,
            }}
          >
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {t("settings.danger.confirmInstruction", {
                emailHint: email ? ` (${email})` : "",
              })}
            </div>
            <input
              className="input"
              type="email"
              placeholder={t("settings.danger.emailPlaceholder")}
              value={confirmEmail}
              onChange={(e) => setConfirmEmail(e.target.value)}
              autoComplete="off"
              style={{ fontSize: 13 }}
            />
            <input
              className="input"
              type="password"
              placeholder={t("settings.danger.passwordPlaceholder")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              style={{ fontSize: 13 }}
            />
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="submit"
                className="btn btn-sm"
                disabled={busy}
                style={{
                  background: "var(--cold)",
                  color: "#fff",
                  border: "none",
                }}
              >
                {busy ? t("settings.danger.deleting") : t("settings.danger.deleteForever")}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setShowDelete(false);
                  setConfirmEmail("");
                  setPassword("");
                }}
                disabled={busy}
              >
                {t("common.cancel")}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

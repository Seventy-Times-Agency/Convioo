"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  deleteAccount,
  gdprExportUrl,
  listAuditLog,
  type AuditLogEntry,
} from "@/lib/api";
import { clearCurrentUser, getCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";

export function PrivacyDataSection() {
  const { t } = useLocale();
  const router = useRouter();
  const [audit, setAudit] = useState<AuditLogEntry[] | null>(null);
  const [showAudit, setShowAudit] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [confirmEmail, setConfirmEmail] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!showAudit || audit !== null) return;
    listAuditLog()
      .then((r) => setAudit(r.items))
      .catch(() => setAudit([]));
  }, [showAudit, audit]);

  const onDelete = async () => {
    setDeleting(true);
    try {
      await deleteAccount({
        confirmEmail: confirmEmail.trim(),
        password: confirmPassword || undefined,
      });
      clearCurrentUser();
      router.push("/");
    } catch (e) {
      const detail =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : t("profile.privacy.deleteFailed");
      showError(detail);
    } finally {
      setDeleting(false);
    }
  };

  const me = getCurrentUser();

  return (
    <div className="card" style={{ padding: 20, marginTop: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Icon name="settings" size={16} style={{ color: "var(--accent)" }} />
        <div style={{ fontSize: 16, fontWeight: 700 }}>
          {t("profile.privacy.title")}
        </div>
      </div>
      <div
        style={{
          fontSize: 13,
          color: "var(--text-muted)",
          marginTop: 4,
          marginBottom: 14,
        }}
      >
        {t("profile.privacy.subtitle")}
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        <a
          className="btn btn-ghost btn-sm"
          href={gdprExportUrl()}
          target="_blank"
          rel="noopener noreferrer"
          style={{ alignSelf: "flex-start" }}
        >
          <Icon name="download" size={13} />
          {t("profile.privacy.export")}
        </a>
        <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
          {t("profile.privacy.exportHint")}
        </div>

        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setShowAudit((v) => !v)}
          style={{ alignSelf: "flex-start", marginTop: 8 }}
        >
          <Icon name={showAudit ? "chevronDown" : "chevronRight"} size={13} />
          {t("profile.privacy.audit")}
        </button>
        {showAudit && (
          <div
            style={{
              fontSize: 12,
              color: "var(--text-muted)",
              maxHeight: 220,
              overflow: "auto",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 8,
            }}
          >
            {audit === null ? (
              <div style={{ padding: 4 }}>{t("common.loading")}</div>
            ) : audit.length === 0 ? (
              <div style={{ padding: 4 }}>
                {t("profile.privacy.auditEmpty")}
              </div>
            ) : (
              audit.map((a) => (
                <div
                  key={a.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 8,
                    padding: "4px 4px",
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  <span style={{ color: "var(--text)" }}>{a.action}</span>
                  <span style={{ color: "var(--text-dim)" }}>
                    {new Date(a.created_at).toLocaleString()}
                  </span>
                </div>
              ))
            )}
          </div>
        )}

        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setShowDelete(true)}
          style={{
            alignSelf: "flex-start",
            marginTop: 16,
            color: "var(--cold)",
            borderColor: "var(--cold)",
          }}
        >
          <Icon name="x" size={13} />
          {t("profile.privacy.delete")}
        </button>
        <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
          {t("profile.privacy.deleteHint")}
        </div>
      </div>

      {showDelete && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            zIndex: 100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
          onClick={() => !deleting && setShowDelete(false)}
        >
          <div
            className="card"
            style={{ padding: 24, maxWidth: 480, width: "100%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                fontSize: 18,
                fontWeight: 700,
                marginBottom: 6,
                color: "var(--cold)",
              }}
            >
              {t("profile.privacy.deleteConfirmTitle")}
            </div>
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
              {t("profile.privacy.deleteConfirmBody")}
            </div>
            <label
              className="eyebrow"
              style={{ display: "block", marginBottom: 4 }}
            >
              {t("profile.privacy.deleteConfirmEmail")}
            </label>
            <input
              className="input"
              value={confirmEmail}
              onChange={(e) => setConfirmEmail(e.target.value)}
              placeholder={me?.email ?? ""}
              autoComplete="off"
              style={{ marginBottom: 12 }}
              disabled={deleting}
            />
            <label
              className="eyebrow"
              style={{ display: "block", marginBottom: 4 }}
            >
              {t("profile.privacy.deleteConfirmPassword")}
            </label>
            <input
              className="input"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="current-password"
              disabled={deleting}
            />
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 8,
                marginTop: 18,
              }}
            >
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowDelete(false)}
                disabled={deleting}
              >
                {t("profile.editor.cancel")}
              </button>
              <button
                type="button"
                className="btn btn-sm"
                style={{
                  background: "var(--cold)",
                  borderColor: "var(--cold)",
                  color: "white",
                }}
                onClick={onDelete}
                disabled={
                  deleting || !confirmEmail.trim() || (me?.email ? false : false)
                }
              >
                {deleting ? t("common.loading") : t("profile.privacy.deleteConfirmCta")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

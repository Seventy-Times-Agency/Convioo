"use client";

import { useState } from "react";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  type CreateReportResult,
  createReport,
  publicReportPdfUrl,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";

/**
 * Wave 4 — "Share report" dialog launched from a search.
 *
 * Lets the user mint a tokenised public report link (optional title +
 * expiry), then surfaces the absolute share URL with a Copy button and
 * a direct PDF download link.
 */
export function ShareReportModal({
  searchId,
  defaultTitle,
  onClose,
}: {
  searchId: string;
  defaultTitle?: string;
  onClose: () => void;
}) {
  const { t } = useLocale();
  const [title, setTitle] = useState(defaultTitle ?? "");
  const [expiry, setExpiry] = useState<"never" | "7" | "30">("never");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CreateReportResult | null>(null);
  const [copied, setCopied] = useState(false);

  const shareUrl = result
    ? `${typeof window !== "undefined" ? window.location.origin : ""}${result.share_path}`
    : "";

  const create = async () => {
    setBusy(true);
    try {
      const res = await createReport(searchId, {
        title: title.trim() || null,
        expiresInDays: expiry === "never" ? null : Number(expiry),
      });
      setResult(res);
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard may be unavailable
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,15,20,0.4)",
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)",
          borderRadius: 16,
          width: "min(460px, 100%)",
          maxHeight: "92vh",
          overflowY: "auto",
          boxShadow: "0 16px 56px rgba(15,15,20,0.18)",
        }}
      >
        <div
          style={{
            padding: "18px 24px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 16,
          }}
        >
          <div>
            <div style={{ fontSize: 17, fontWeight: 700 }}>
              {t("shareReport.title")}
            </div>
            <div
              style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}
            >
              {t("shareReport.subtitle")}
            </div>
          </div>
          <button className="btn-icon" onClick={onClose} type="button">
            <Icon name="x" size={18} />
          </button>
        </div>

        <div style={{ padding: 24 }}>
          {!result ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label
                  className="eyebrow"
                  style={{ display: "block", marginBottom: 6 }}
                >
                  {t("shareReport.titleField")}
                </label>
                <input
                  type="text"
                  className="input"
                  value={title}
                  maxLength={160}
                  placeholder={t("shareReport.titlePlaceholder")}
                  onChange={(e) => setTitle(e.target.value)}
                  style={{ width: "100%" }}
                />
              </div>

              <div>
                <label
                  className="eyebrow"
                  style={{ display: "block", marginBottom: 6 }}
                >
                  {t("shareReport.expiry")}
                </label>
                <select
                  className="select"
                  value={expiry}
                  onChange={(e) =>
                    setExpiry(e.target.value as "never" | "7" | "30")
                  }
                  style={{ width: "100%" }}
                >
                  <option value="never">{t("shareReport.expiry.never")}</option>
                  <option value="7">{t("shareReport.expiry.7")}</option>
                  <option value="30">{t("shareReport.expiry.30")}</option>
                </select>
              </div>

              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={create}
              >
                {busy ? t("common.loading") : t("shareReport.create")}
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div
                style={{
                  fontSize: 13,
                  color: "var(--text-muted)",
                  lineHeight: 1.5,
                }}
              >
                {t("shareReport.ready")}
              </div>

              <div>
                <label
                  className="eyebrow"
                  style={{ display: "block", marginBottom: 6 }}
                >
                  {t("shareReport.linkLabel")}
                </label>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    type="text"
                    className="input"
                    readOnly
                    value={shareUrl}
                    onFocus={(e) => e.currentTarget.select()}
                    style={{ flex: 1, fontSize: 12.5 }}
                  />
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={copy}
                  >
                    <Icon name="copy" size={14} />
                    {copied ? t("common.copied") : t("common.copy")}
                  </button>
                </div>
              </div>

              <a
                className="btn btn-ghost btn-sm"
                href={publicReportPdfUrl(result.token)}
                target="_blank"
                rel="noopener noreferrer"
                style={{ alignSelf: "flex-start" }}
              >
                <Icon name="download" size={14} /> {t("shareReport.downloadPdf")}
              </a>

              {result.expires_at && (
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {t("shareReport.expiresOn", {
                    date: new Date(result.expires_at).toLocaleDateString(),
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

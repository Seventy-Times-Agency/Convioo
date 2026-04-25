"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { ApiError, resendVerification } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";

/**
 * Soft gate banner shown on every /app/* page when the signed-in
 * user hasn't verified their email yet. Search creation is
 * server-side blocked (403) until they confirm; the banner is the
 * UX nudge to do it.
 *
 * Local "dismiss" only hides the banner for the current tab — the
 * server-side gate is what actually matters.
 */
export function VerifyEmailBanner() {
  const { t } = useLocale();
  const [needsVerify, setNeedsVerify] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const user = getCurrentUser();
    if (!user) return;
    setEmail(user.email ?? null);
    setNeedsVerify(user.email !== undefined && user.email_verified === false);
  }, []);

  if (!needsVerify || !email) return null;

  const resend = async () => {
    setSending(true);
    setError(null);
    try {
      await resendVerification(email);
      setSent(true);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      style={{
        position: "sticky",
        top: 0,
        zIndex: 60,
        padding: "10px 20px",
        background:
          "linear-gradient(135deg, color-mix(in srgb, #F59E0B 14%, var(--surface)), var(--surface))",
        borderBottom: "1px solid color-mix(in srgb, #F59E0B 30%, var(--border))",
        display: "flex",
        alignItems: "center",
        gap: 12,
        fontSize: 13,
      }}
    >
      <Icon name="mail" size={16} style={{ color: "#B45309" }} />
      <div style={{ flex: 1, lineHeight: 1.45 }}>
        <span style={{ color: "var(--text)", fontWeight: 600 }}>
          {t("verifyBanner.title", { email })}
        </span>
        <span style={{ color: "var(--text-muted)", marginLeft: 6 }}>
          {t("verifyBanner.body")}
        </span>
      </div>
      {sent ? (
        <span style={{ color: "var(--hot)", fontSize: 12 }}>
          {t("verifyBanner.sent")}
        </span>
      ) : (
        <button
          type="button"
          className="btn btn-sm"
          onClick={resend}
          disabled={sending}
          style={{ flexShrink: 0 }}
        >
          {sending ? t("common.loading") : t("verifyBanner.resend")}
        </button>
      )}
      {error && (
        <span style={{ fontSize: 12, color: "var(--cold)" }}>{error}</span>
      )}
    </div>
  );
}

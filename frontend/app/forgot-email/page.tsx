"use client";

import { useState } from "react";
import Link from "next/link";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { ApiError, forgotEmail } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

export default function ForgotEmailPage() {
  const { t } = useLocale();
  const [recovery, setRecovery] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!recovery.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      await forgotEmail(recovery.trim().toLowerCase());
      setDone(true);
    } catch (e) {
      const detail =
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(detail);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell title={t("auth.forgotEmail.title")}>
      {done ? (
        <div>
          <p style={{ color: "var(--text-muted)", lineHeight: 1.55, fontSize: 15 }}>
            {t("auth.forgotEmail.doneBody")}
          </p>
          <p style={{ marginTop: 18, fontSize: 13 }}>
            <Link href="/login" style={{ color: "var(--accent)", fontWeight: 600 }}>
              ← {t("auth.backToLogin")}
            </Link>
          </p>
        </div>
      ) : (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <p style={{ color: "var(--text-muted)", marginBottom: 6, fontSize: 14, lineHeight: 1.55 }}>
            {t("auth.forgotEmail.intro")}
          </p>
          <Field label={t("auth.field.recoveryEmail")}>
            <input
              className="input"
              type="email"
              value={recovery}
              onChange={(e) => setRecovery(e.target.value)}
              placeholder="[email protected]"
              autoFocus
              autoComplete="email"
            />
          </Field>
          {error && <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>}
          <button
            type="submit"
            className="btn btn-lg"
            disabled={submitting || !recovery.trim()}
            style={{ justifyContent: "center", marginTop: 6 }}
          >
            {submitting ? t("auth.forgotEmail.submitting") : t("auth.forgotEmail.submit")}{" "}
            <Icon name="arrow" size={15} />
          </button>
          <div style={{ marginTop: 14, fontSize: 13, color: "var(--text-muted)" }}>
            <Link href="/login" style={{ color: "var(--accent)", fontWeight: 600 }}>
              ← {t("auth.backToLogin")}
            </Link>
            {"  ·  "}
            <Link href="/forgot-password" style={{ color: "var(--accent)", fontWeight: 600 }}>
              {t("auth.forgotPasswordLink")}
            </Link>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
            {t("auth.forgotEmail.noRecoveryPre")}{" "}
            <a href="mailto:[email protected]" style={{ color: "var(--accent)" }}>
              [email protected]
            </a>{" "}
            {t("auth.forgotEmail.noRecoveryPost")}
          </p>
        </form>
      )}
    </AuthShell>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: "var(--text-muted)",
          marginBottom: 6,
          display: "block",
        }}
      >
        {label}
      </label>
      {children}
    </div>
  );
}

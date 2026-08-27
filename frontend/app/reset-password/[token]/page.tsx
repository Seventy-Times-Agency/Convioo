"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { ApiError, resetPassword } from "@/lib/api";
import { setCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";

export default function ResetPasswordPage() {
  const { t } = useLocale();
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const token = String(params?.token ?? "");
  const [pwd1, setPwd1] = useState("");
  const [pwd2, setPwd2] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (pwd1.length < 8) {
      setError(t("auth.resetPassword.tooShort"));
      return;
    }
    if (pwd1 !== pwd2) {
      setError(t("auth.passwordsDontMatch"));
      return;
    }
    setSubmitting(true);
    try {
      const user = await resetPassword(token, pwd1);
      setCurrentUser(user);
      setDone(true);
      setTimeout(() => router.push("/app"), 1200);
    } catch (e) {
      let detail =
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      if (e instanceof ApiError && (e.status === 404 || e.status === 410)) {
        detail = t("auth.resetPassword.linkExpired");
      }
      setError(detail);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell title={t("auth.resetPassword.title")}>
      {done ? (
        <div>
          <p style={{ color: "var(--text-muted)", lineHeight: 1.55, fontSize: 15 }}>
            {t("auth.resetPassword.doneBody")}
          </p>
        </div>
      ) : (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <p style={{ color: "var(--text-muted)", marginBottom: 6, fontSize: 14, lineHeight: 1.55 }}>
            {t("auth.resetPassword.intro")}
          </p>
          <Field label={t("auth.field.newPassword")}>
            <input
              className="input"
              type="password"
              value={pwd1}
              onChange={(e) => setPwd1(e.target.value)}
              placeholder={t("auth.field.newPasswordPh")}
              autoFocus
              autoComplete="new-password"
            />
          </Field>
          <Field label={t("auth.field.repeatPassword")}>
            <input
              className="input"
              type="password"
              value={pwd2}
              onChange={(e) => setPwd2(e.target.value)}
              placeholder={t("auth.field.repeatPasswordPh")}
              autoComplete="new-password"
            />
          </Field>
          {error && <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>}
          <button
            type="submit"
            className="btn btn-lg"
            disabled={submitting || !pwd1 || !pwd2}
            style={{ justifyContent: "center", marginTop: 6 }}
          >
            {submitting ? t("auth.resetPassword.submitting") : t("auth.resetPassword.submit")}{" "}
            <Icon name="arrow" size={15} />
          </button>
          <div style={{ marginTop: 14, fontSize: 13, color: "var(--text-muted)" }}>
            <Link href="/login" style={{ color: "var(--accent)", fontWeight: 600 }}>
              ← {t("auth.backToLogin")}
            </Link>
          </div>
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

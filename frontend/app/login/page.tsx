"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { ApiError, loginUser } from "@/lib/api";
import { setCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";

const RETURN_KEY = "convioo.returnTo";

function consumeReturnTo(): string | null {
  if (typeof window === "undefined") return null;
  let raw = window.localStorage.getItem(RETURN_KEY);
  if (!raw) raw = window.localStorage.getItem("leadgen.returnTo");
  window.localStorage.removeItem(RETURN_KEY);
  window.localStorage.removeItem("leadgen.returnTo");
  return raw;
}

export default function LoginPage() {
  const { t } = useLocale();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim() || !password) return;
    setError(null);
    setSubmitting(true);
    try {
      const user = await loginUser(email.trim().toLowerCase(), password);
      setCurrentUser(user);
      router.push(consumeReturnTo() ?? "/app");
    } catch (e) {
      let detail =
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      if (e instanceof ApiError && e.status === 401) {
        detail = t("auth.login.invalid");
      }
      setError(detail);
      setSubmitting(false);
    }
  };

  const disabled = submitting || !email.trim() || !password;

  return (
    <AuthShell title={t("auth.login.title")}>
      <div style={{ color: "var(--text-muted)", marginBottom: 24, fontSize: 15 }}>
        {t("auth.login.subtitle")}
      </div>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <Field label={t("auth.field.email")}>
          <input
            className="input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("auth.field.emailPh")}
            autoFocus
            autoComplete="email"
          />
        </Field>
        <Field label={t("auth.field.password")}>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("auth.field.passwordPh")}
            autoComplete="current-password"
          />
        </Field>

        {error && (
          <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>
        )}

        <button
          type="submit"
          className="btn btn-lg"
          disabled={disabled}
          style={{
            justifyContent: "center",
            opacity: disabled ? 0.5 : 1,
            marginTop: 6,
          }}
        >
          {submitting ? t("common.loading") : t("auth.login.submit")}{" "}
          <Icon name="arrow" size={15} />
        </button>
      </form>

      <div style={{ marginTop: 22, fontSize: 13, color: "var(--text-muted)" }}>
        {t("auth.login.noAccount")}{" "}
        <Link href="/register" style={{ color: "var(--accent)", fontWeight: 600 }}>
          {t("auth.login.registerLink")}
        </Link>
      </div>
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

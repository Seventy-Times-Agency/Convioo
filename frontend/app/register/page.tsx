"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { ApiError, registerUser } from "@/lib/api";
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

export default function RegisterPage() {
  const { t } = useLocale();
  const router = useRouter();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (
      !firstName.trim() ||
      !lastName.trim() ||
      !email.trim() ||
      password.length < 8
    )
      return;
    setError(null);
    setSubmitting(true);
    try {
      const user = await registerUser({
        firstName: firstName.trim(),
        lastName: lastName.trim(),
        email: email.trim().toLowerCase(),
        password,
      });
      setCurrentUser(user);
      // Always send the new account through onboarding first; the
      // verify-email banner stays visible across /app until the link
      // is clicked.
      const returnTo = consumeReturnTo();
      router.push(returnTo ?? (user.onboarded ? "/app" : "/onboarding"));
    } catch (e) {
      const detail =
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(detail);
      setSubmitting(false);
    }
  };

  const disabled =
    submitting ||
    !firstName.trim() ||
    !lastName.trim() ||
    !email.trim() ||
    password.length < 8;

  return (
    <AuthShell title={t("auth.register.title")}>
      <div style={{ color: "var(--text-muted)", marginBottom: 24, fontSize: 15 }}>
        {t("auth.register.subtitle")}
      </div>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <Field label={t("auth.field.firstName")}>
            <input
              className="input"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder={t("auth.field.firstNamePh")}
              autoFocus
              autoComplete="given-name"
            />
          </Field>
          <Field label={t("auth.field.lastName")}>
            <input
              className="input"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder={t("auth.field.lastNamePh")}
              autoComplete="family-name"
            />
          </Field>
        </div>
        <Field label={t("auth.field.email")}>
          <input
            className="input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("auth.field.emailPh")}
            autoComplete="email"
          />
        </Field>
        <Field
          label={t("auth.field.password")}
          hint={t("auth.field.passwordHint")}
        >
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("auth.field.passwordPh")}
            autoComplete="new-password"
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
          {submitting ? t("common.loading") : t("auth.register.submit")}{" "}
          <Icon name="arrow" size={15} />
        </button>
      </form>

      <div style={{ marginTop: 22, fontSize: 13, color: "var(--text-muted)" }}>
        {t("auth.register.haveAccount")}{" "}
        <Link href="/login" style={{ color: "var(--accent)", fontWeight: 600 }}>
          {t("auth.register.signInLink")}
        </Link>
      </div>
    </AuthShell>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: "var(--text-muted)",
          marginBottom: 6,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <span>{label}</span>
        {hint && (
          <span style={{ fontSize: 10.5, color: "var(--text-dim)", fontWeight: 500 }}>
            {hint}
          </span>
        )}
      </label>
      {children}
    </div>
  );
}

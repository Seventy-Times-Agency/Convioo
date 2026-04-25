"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { ApiError, loginUser } from "@/lib/api";
import { setCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";

export default function LoginPage() {
  const { t } = useLocale();
  const router = useRouter();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!firstName.trim() || !lastName.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      const user = await loginUser(firstName.trim(), lastName.trim());
      setCurrentUser(user);
      router.push(user.onboarded ? "/app" : "/onboarding");
    } catch (e) {
      let detail =
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      if (e instanceof ApiError && e.status === 404) {
        detail = t("auth.login.notFound");
      }
      setError(detail);
      setSubmitting(false);
    }
  };

  const disabled = submitting || !firstName.trim() || !lastName.trim();

  return (
    <AuthShell title={t("auth.login.title")}>
      <div style={{ color: "var(--text-muted)", marginBottom: 24, fontSize: 15 }}>
        {t("auth.login.subtitle")}
      </div>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
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

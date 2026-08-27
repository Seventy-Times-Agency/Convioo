"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { ApiError, registerUser } from "@/lib/api";
import { setCurrentUser } from "@/lib/auth";
import { useLocale, type TranslationKey } from "@/lib/i18n";

const RETURN_KEY = "convioo.returnTo";

function consumeReturnTo(): string | null {
  if (typeof window === "undefined") return null;
  let raw = window.localStorage.getItem(RETURN_KEY);
  if (!raw) raw = window.localStorage.getItem("leadgen.returnTo");
  window.localStorage.removeItem(RETURN_KEY);
  window.localStorage.removeItem("leadgen.returnTo");
  return raw;
}

const GENDER_OPTIONS: { code: string; labelKey: TranslationKey }[] = [
  { code: "male", labelKey: "auth.field.gender.male" },
  { code: "female", labelKey: "auth.field.gender.female" },
  { code: "other", labelKey: "auth.field.gender.other" },
];

const AGE_OPTIONS: { code: string; labelKey: TranslationKey }[] = [
  { code: "<18", labelKey: "onboarding.age.lt18" },
  { code: "18-24", labelKey: "onboarding.age.18_24" },
  { code: "25-34", labelKey: "onboarding.age.25_34" },
  { code: "35-44", labelKey: "onboarding.age.35_44" },
  { code: "45-54", labelKey: "onboarding.age.45_54" },
  { code: "55+", labelKey: "onboarding.age.55plus" },
];

export default function RegisterPage() {
  const { t } = useLocale();
  const router = useRouter();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [registrationPassword, setRegistrationPassword] = useState("");
  const [ageRange, setAgeRange] = useState<string | null>(null);
  const [gender, setGender] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (
      !firstName.trim() ||
      !lastName.trim() ||
      !email.trim() ||
      password.length < 8 ||
      !registrationPassword.trim()
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
        ageRange,
        gender,
        registrationPassword: registrationPassword.trim(),
      });
      setCurrentUser(user);
      // Backend stamps onboarded_at on register, so the user lands on
      // /app immediately; the soft profile-nudge banner there walks
      // them through filling the rest of the profile. The verify-email
      // banner stays visible across /app until the link is clicked.
      const returnTo = consumeReturnTo();
      router.push(returnTo ?? "/app");
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
    password.length < 8 ||
    !registrationPassword.trim();

  return (
    <AuthShell title={t("auth.register.title")}>
      <div style={{ color: "var(--text-muted)", marginBottom: 24, fontSize: 15 }}>
        {t("auth.register.subtitle")}
      </div>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <Field
          label={t("auth.field.inviteCode")}
          hint={t("auth.field.inviteCodeHint")}
        >
          <input
            className="input"
            value={registrationPassword}
            onChange={(e) => setRegistrationPassword(e.target.value)}
            placeholder={t("auth.field.inviteCodePh")}
            autoComplete="off"
          />
        </Field>
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
        <Field
          label={t("auth.field.age")}
          hint={t("auth.field.ageHint")}
        >
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {AGE_OPTIONS.map((opt) => {
              const active = ageRange === opt.code;
              return (
                <button
                  key={opt.code}
                  type="button"
                  onClick={() => setAgeRange(active ? null : opt.code)}
                  style={{
                    padding: "7px 13px",
                    fontSize: 13,
                    borderRadius: 999,
                    cursor: "pointer",
                    border: active
                      ? "1px solid var(--accent)"
                      : "1px solid var(--border)",
                    background: active
                      ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                      : "var(--surface)",
                    color: active ? "var(--accent)" : "var(--text)",
                    fontWeight: active ? 600 : 500,
                  }}
                >
                  {t(opt.labelKey)}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => setAgeRange(null)}
              style={{
                padding: "7px 13px",
                fontSize: 13,
                borderRadius: 999,
                cursor: "pointer",
                border: "1px solid transparent",
                background: "transparent",
                color: "var(--text-dim)",
                fontWeight: 500,
              }}
            >
              {t("auth.field.ageSkip")}
            </button>
          </div>
        </Field>
        <Field
          label={t("auth.field.gender")}
          hint={t("auth.field.genderHint")}
        >
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {GENDER_OPTIONS.map((opt) => {
              const active = gender === opt.code;
              return (
                <button
                  key={opt.code}
                  type="button"
                  onClick={() => setGender(active ? null : opt.code)}
                  style={{
                    padding: "7px 13px",
                    fontSize: 13,
                    borderRadius: 999,
                    cursor: "pointer",
                    border: active
                      ? "1px solid var(--accent)"
                      : "1px solid var(--border)",
                    background: active
                      ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                      : "var(--surface)",
                    color: active ? "var(--accent)" : "var(--text)",
                    fontWeight: active ? 600 : 500,
                  }}
                >
                  {t(opt.labelKey)}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => setGender(null)}
              style={{
                padding: "7px 13px",
                fontSize: 13,
                borderRadius: 999,
                cursor: "pointer",
                border: "1px solid transparent",
                background: "transparent",
                color: "var(--text-dim)",
                fontWeight: 500,
              }}
            >
              {t("auth.field.genderSkip")}
            </button>
          </div>
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

"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { ApiError, changeEmail, changePassword } from "@/lib/api";
import { getCurrentUser, setCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";

export function AccountSection() {
  const { t } = useLocale();
  const [email, setEmail] = useState<string | null>(null);
  const [verified, setVerified] = useState(false);
  const [emailEditing, setEmailEditing] = useState(false);
  const [pwdEditing, setPwdEditing] = useState(false);

  useEffect(() => {
    const u = getCurrentUser();
    if (!u) return;
    setEmail(u.email ?? null);
    setVerified(u.email_verified === true);
  }, []);

  if (!email) return null;

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.account")}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
          paddingBottom: emailEditing ? 12 : 0,
          marginBottom: emailEditing ? 16 : 18,
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="eyebrow" style={{ marginBottom: 4 }}>
            {t("settings.account.emailLabel")}
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 14,
              fontFamily: "var(--font-mono)",
            }}
          >
            <span>{email}</span>
            <span
              className="chip"
              style={{
                fontSize: 10,
                padding: "2px 7px",
                background: verified ? "var(--accent-soft)" : "transparent",
                color: verified ? "var(--accent)" : "var(--text-dim)",
                border: verified
                  ? "1px solid color-mix(in srgb, var(--accent) 30%, transparent)"
                  : "1px solid var(--border)",
              }}
            >
              {verified
                ? t("settings.account.verified")
                : t("settings.account.unverified")}
            </span>
          </div>
        </div>
        {!emailEditing && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setEmailEditing(true)}
          >
            <Icon name="pencil" size={13} />
            {t("settings.account.changeEmail")}
          </button>
        )}
      </div>

      {emailEditing && (
        <ChangeEmailForm
          currentEmail={email}
          onCancel={() => setEmailEditing(false)}
          onSent={(pending) => {
            setEmailEditing(false);
            void pending;
          }}
        />
      )}

      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="eyebrow" style={{ marginBottom: 4 }}>
            {t("settings.account.passwordLabel")}
          </div>
          <div style={{ fontSize: 13.5, color: "var(--text-muted)" }}>
            {t("settings.account.passwordHelp")}
          </div>
        </div>
        {!pwdEditing && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setPwdEditing(true)}
          >
            <Icon name="pencil" size={13} />
            {t("settings.account.changePassword")}
          </button>
        )}
      </div>

      {pwdEditing && (
        <ChangePasswordForm
          onCancel={() => setPwdEditing(false)}
          onSaved={() => setPwdEditing(false)}
        />
      )}
    </div>
  );
}

function ChangeEmailForm({
  currentEmail,
  onCancel,
  onSent,
}: {
  currentEmail: string;
  onCancel: () => void;
  onSent: (pendingEmail: string) => void;
}) {
  const { t } = useLocale();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next = email.trim().toLowerCase();
    if (!next || !password) return;
    if (next === currentEmail.toLowerCase()) {
      setErr(t("settings.account.sameEmail"));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await changeEmail(next, password);
      setDone(next);
      onSent(next);
    } catch (e) {
      setErr(
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div
        style={{
          padding: 12,
          borderRadius: 10,
          background: "color-mix(in srgb, var(--accent) 8%, transparent)",
          border:
            "1px solid color-mix(in srgb, var(--accent) 25%, var(--border))",
          fontSize: 13.5,
          marginBottom: 18,
          display: "flex",
          alignItems: "flex-start",
          gap: 10,
        }}
      >
        <Icon name="mail" size={14} style={{ color: "var(--accent)", marginTop: 2 }} />
        <div style={{ lineHeight: 1.5 }}>
          {t("settings.account.changeEmailSent", { email: done })}
        </div>
      </div>
    );
  }

  return (
    <form
      onSubmit={submit}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        marginBottom: 18,
      }}
    >
      <input
        className="input"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder={t("settings.account.newEmailPh")}
        autoComplete="email"
      />
      <input
        className="input"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder={t("settings.account.passwordConfirmPh")}
        autoComplete="current-password"
      />
      {err && <div style={{ fontSize: 12.5, color: "var(--cold)" }}>{err}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button
          type="submit"
          className="btn btn-sm"
          disabled={busy || !email.trim() || !password}
        >
          {busy ? t("common.loading") : t("settings.account.sendVerify")}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onCancel}
          disabled={busy}
        >
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );
}

function ChangePasswordForm({
  onCancel,
  onSaved,
}: {
  onCancel: () => void;
  onSaved: () => void;
}) {
  const { t } = useLocale();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!current || next.length < 8) return;
    if (next !== confirm) {
      setErr(t("settings.account.passwordsDontMatch"));
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const updated = await changePassword(current, next);
      const local = getCurrentUser();
      if (local) {
        setCurrentUser({
          ...local,
          email: updated.email,
          email_verified: updated.email_verified,
          onboarded: updated.onboarded,
        });
      }
      setDone(true);
      setTimeout(onSaved, 800);
    } catch (e) {
      setErr(
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div
        style={{
          padding: 12,
          borderRadius: 10,
          background: "color-mix(in srgb, var(--hot) 8%, transparent)",
          border:
            "1px solid color-mix(in srgb, var(--hot) 25%, var(--border))",
          fontSize: 13.5,
          marginTop: 12,
          color: "var(--hot)",
        }}
      >
        {t("settings.account.passwordSaved")}
      </div>
    );
  }

  return (
    <form
      onSubmit={submit}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        marginTop: 12,
      }}
    >
      <input
        className="input"
        type="password"
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        placeholder={t("settings.account.currentPasswordPh")}
        autoComplete="current-password"
      />
      <input
        className="input"
        type="password"
        value={next}
        onChange={(e) => setNext(e.target.value)}
        placeholder={t("settings.account.newPasswordPh")}
        autoComplete="new-password"
      />
      <input
        className="input"
        type="password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        placeholder={t("settings.account.confirmPasswordPh")}
        autoComplete="new-password"
      />
      {err && <div style={{ fontSize: 12.5, color: "var(--cold)" }}>{err}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button
          type="submit"
          className="btn btn-sm"
          disabled={busy || !current || next.length < 8 || !confirm}
        >
          {busy ? t("common.loading") : t("common.save")}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onCancel}
          disabled={busy}
        >
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );
}

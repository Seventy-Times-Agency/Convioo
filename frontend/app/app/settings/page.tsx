"use client";

import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  changeEmail,
  changePassword,
  listMySessions,
  logoutAllSessions,
  revokeMySession,
  setRecoveryEmail,
  type SessionInfo,
} from "@/lib/api";
import { getCurrentUser, setCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";
import {
  WORKSPACE_TINTS,
  getWorkspaceTint,
  setWorkspaceTint,
  type WorkspaceTint,
} from "@/lib/tint";
import {
  getActiveWorkspace,
  subscribeWorkspace,
  type Workspace,
} from "@/lib/workspace";

interface HealthSummary {
  status: string;
  db: boolean;
  commit: string;
}

export default function SettingsPage() {
  const { t } = useLocale();
  const [health, setHealth] = useState<HealthSummary | null>(null);
  const [queueEnabled, setQueueEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_API_URL ?? "";
    if (!base) return;
    const root = base.replace(/\/$/, "");
    fetch(`${root}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
    fetch(`${root}/api/v1/queue/status`)
      .then((r) => r.json())
      .then((b) => setQueueEnabled(b.queue_enabled))
      .catch(() => setQueueEnabled(null));
  }, []);

  const integrations: Array<{
    name: string;
    status: "connected" | "pending";
    detail?: string;
  }> = [
    {
      name: t("settings.int.googlePlaces"),
      status: "connected",
      detail: "GOOGLE_PLACES_API_KEY",
    },
    {
      name: t("settings.int.anthropic"),
      status: "connected",
      detail: "ANTHROPIC_API_KEY",
    },
    {
      name: t("settings.int.telegram"),
      status: "connected",
      detail: "BOT_TOKEN",
    },
    {
      name: t("settings.int.redis"),
      status: queueEnabled ? "connected" : "pending",
      detail: queueEnabled
        ? t("settings.int.redis.connected")
        : t("settings.int.redis.fallback"),
    },
    {
      name: t("settings.int.email"),
      status: "pending",
      detail: t("settings.int.email.planned"),
    },
  ];

  return (
    <>
      <Topbar title={t("settings.title")} subtitle={t("settings.subtitle")} />
      <div className="page" style={{ maxWidth: 720 }}>
        <AccountSection />

        <SecuritySection />

        <TintSection />

        <div className="card" style={{ padding: 24, marginBottom: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("settings.workspace")}
          </div>
          <KV label={t("settings.workspaceName")} value="Convioo" />
          <div style={{ marginTop: 16 }}>
            <KV label={t("settings.auth")} value={t("settings.authValue")} />
          </div>
        </div>

        <div className="card" style={{ padding: 24, marginBottom: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("settings.backend")}
          </div>
          <KV
            label={t("settings.health")}
            value={
              health
                ? `${health.status} · db=${health.db ? "ok" : "down"}`
                : t("settings.unknown")
            }
          />
          <div style={{ marginTop: 16 }}>
            <KV
              label={t("settings.commit")}
              value={health?.commit ?? t("settings.unknown")}
              mono
            />
          </div>
        </div>

        <div className="card" style={{ padding: 24 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("settings.integrations")}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {integrations.map((i, k) => (
              <div
                key={i.name}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "10px 0",
                  borderBottom:
                    k < integrations.length - 1
                      ? "1px solid var(--border)"
                      : "none",
                }}
              >
                <div>
                  <div style={{ fontSize: 14 }}>{i.name}</div>
                  {i.detail && (
                    <div style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
                      {i.detail}
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span
                    className="status-dot"
                    style={{
                      background:
                        i.status === "connected"
                          ? "var(--hot)"
                          : "var(--text-dim)",
                    }}
                  />
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {i.status === "connected"
                      ? t("settings.int.connected")
                      : t("settings.int.notConfigured")}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card" style={{ padding: 24, marginTop: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t("settings.connectors")}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {(
              [
                {
                  key: "gmail",
                  icon: "mail" as const,
                  name: t("settings.connector.gmail"),
                  desc: t("settings.connector.gmail.desc"),
                },
                {
                  key: "outlook",
                  icon: "mail" as const,
                  name: t("settings.connector.outlook"),
                  desc: t("settings.connector.outlook.desc"),
                },
                {
                  key: "smtp",
                  icon: "send" as const,
                  name: t("settings.connector.smtp"),
                  desc: t("settings.connector.smtp.desc"),
                },
              ]
            ).map((c) => (
              <div
                key={c.key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 14px",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  background: "var(--surface-2)",
                  opacity: 0.85,
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    display: "grid",
                    placeItems: "center",
                    color: "var(--text-muted)",
                    flexShrink: 0,
                  }}
                >
                  <Icon name={c.icon} size={15} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{c.name}</div>
                  <div
                    style={{
                      fontSize: 11.5,
                      color: "var(--text-dim)",
                      marginTop: 2,
                      lineHeight: 1.45,
                    }}
                  >
                    {c.desc}
                  </div>
                </div>
                <span
                  className="chip"
                  style={{
                    fontSize: 10,
                    color: "var(--text-dim)",
                    flexShrink: 0,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                  }}
                >
                  {t("settings.connector.soon")}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled
                  style={{ flexShrink: 0 }}
                >
                  {t("settings.connector.connect")}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function KV({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        {label}
      </div>
      <div
        style={{
          fontSize: 14,
          fontFamily: mono ? "var(--font-mono)" : undefined,
        }}
      >
        {value}
      </div>
    </div>
  );
}

function SecuritySection() {
  const [recoveryMasked, setRecoveryMasked] = useState<string | null>(null);
  const [recoveryDraft, setRecoveryDraft] = useState("");
  const [editingRecovery, setEditingRecovery] = useState(false);
  const [recoveryBusy, setRecoveryBusy] = useState(false);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);
  const [recoveryToast, setRecoveryToast] = useState<string | null>(null);

  const [sessions, setSessions] = useState<SessionInfo[] | null>(null);
  const [sessionsBusy, setSessionsBusy] = useState(false);
  const [logoutAllBusy, setLogoutAllBusy] = useState(false);

  const refreshSessions = async () => {
    setSessionsBusy(true);
    try {
      const result = await listMySessions();
      setSessions(result.sessions);
    } catch {
      setSessions([]);
    } finally {
      setSessionsBusy(false);
    }
  };

  useEffect(() => {
    void refreshSessions();
    // Pull profile so we know the masked recovery email.
    const id = getCurrentUser()?.user_id;
    if (!id) return;
    fetch(`/api/v1/users/${id}`, { credentials: "include" })
      .then((r) => r.json())
      .then((p) => {
        if (typeof p?.recovery_email_masked === "string") {
          setRecoveryMasked(p.recovery_email_masked);
        } else {
          setRecoveryMasked(null);
        }
      })
      .catch(() => {});
  }, []);

  const saveRecovery = async (event: React.FormEvent) => {
    event.preventDefault();
    setRecoveryError(null);
    setRecoveryToast(null);
    setRecoveryBusy(true);
    try {
      const value = recoveryDraft.trim().toLowerCase() || null;
      const profile = await setRecoveryEmail(value);
      setRecoveryMasked(profile.recovery_email_masked);
      setRecoveryDraft("");
      setEditingRecovery(false);
      setRecoveryToast(value ? "Резервный email сохранён" : "Резервный email удалён");
    } catch (e) {
      setRecoveryError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e),
      );
    } finally {
      setRecoveryBusy(false);
    }
  };

  const clearRecovery = async () => {
    if (!confirm("Удалить резервный email? Восстановление через него станет недоступно.")) return;
    setRecoveryBusy(true);
    setRecoveryError(null);
    try {
      const profile = await setRecoveryEmail(null);
      setRecoveryMasked(profile.recovery_email_masked);
      setRecoveryToast("Резервный email удалён");
    } catch (e) {
      setRecoveryError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e),
      );
    } finally {
      setRecoveryBusy(false);
    }
  };

  const revoke = async (sid: string) => {
    setSessionsBusy(true);
    try {
      await revokeMySession(sid);
      await refreshSessions();
    } catch {
      // best effort — surface via toast later
    } finally {
      setSessionsBusy(false);
    }
  };

  const logoutAll = async () => {
    if (!confirm("Завершить все сессии кроме текущей?")) return;
    setLogoutAllBusy(true);
    try {
      const r = await logoutAllSessions();
      await refreshSessions();
      alert(`Завершено сессий: ${r.revoked}`);
    } finally {
      setLogoutAllBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Безопасность
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
          paddingBottom: editingRecovery ? 12 : 0,
          marginBottom: 18,
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="eyebrow" style={{ marginBottom: 4 }}>
            Резервный email
          </div>
          <div style={{ fontSize: 13.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
            {recoveryMasked
              ? `Привязан: ${recoveryMasked}. Используется когда вы забыли основной email.`
              : "Если потеряете доступ к основному email, мы пришлём напоминание сюда. Не отображается публично."}
          </div>
          {recoveryToast && (
            <div style={{ fontSize: 12, color: "var(--accent)", marginTop: 6 }}>{recoveryToast}</div>
          )}
        </div>
        {!editingRecovery && (
          <div style={{ display: "flex", gap: 6 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setRecoveryDraft("");
                setEditingRecovery(true);
                setRecoveryToast(null);
              }}
            >
              <Icon name="pencil" size={13} />
              {recoveryMasked ? "Сменить" : "Добавить"}
            </button>
            {recoveryMasked && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => void clearRecovery()}
                disabled={recoveryBusy}
                style={{ color: "var(--cold)" }}
              >
                Удалить
              </button>
            )}
          </div>
        )}
      </div>

      {editingRecovery && (
        <form onSubmit={saveRecovery} style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 18 }}>
          <input
            className="input"
            type="email"
            value={recoveryDraft}
            onChange={(e) => setRecoveryDraft(e.target.value)}
            placeholder="[email protected]"
            autoFocus
          />
          {recoveryError && <div style={{ fontSize: 13, color: "var(--cold)" }}>{recoveryError}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="submit"
              className="btn btn-sm"
              disabled={recoveryBusy || !recoveryDraft.trim()}
            >
              {recoveryBusy ? "Сохраняем…" : "Сохранить"}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setEditingRecovery(false)}
            >
              Отмена
            </button>
          </div>
        </form>
      )}

      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 14,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="eyebrow" style={{ marginBottom: 4 }}>
            Активные сессии
          </div>
          <div style={{ fontSize: 13.5, color: "var(--text-muted)" }}>
            Где вы сейчас вошли. Завершите неизвестные устройства.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => void logoutAll()}
          disabled={logoutAllBusy}
          style={{ color: "var(--cold)" }}
        >
          {logoutAllBusy ? "…" : "Выйти везде кроме здесь"}
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {sessions === null && (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
        )}
        {sessions && sessions.length === 0 && (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Нет активных сессий.</div>
        )}
        {sessions?.map((s) => {
          const last = new Date(s.last_seen_at).toLocaleString();
          return (
            <div
              key={s.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 10,
                padding: 12,
                display: "flex",
                gap: 12,
                alignItems: "flex-start",
                background: s.current ? "var(--accent-soft)" : "transparent",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {s.user_agent ? trimUA(s.user_agent) : "Неизвестное устройство"}
                  {s.current && (
                    <span
                      className="chip"
                      style={{
                        marginLeft: 8,
                        fontSize: 10,
                        padding: "2px 6px",
                        background: "var(--accent)",
                        color: "white",
                      }}
                    >
                      сейчас
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                  IP: {s.ip ?? "—"} · последняя активность: {last}
                </div>
              </div>
              {!s.current && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => void revoke(s.id)}
                  disabled={sessionsBusy}
                  style={{ color: "var(--cold)" }}
                >
                  Завершить
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function trimUA(ua: string): string {
  // Cheap "what browser is this" heuristic so the UI shows something
  // human-readable instead of the full 200-char string.
  if (/Edg\//.test(ua)) return "Edge";
  if (/OPR\//.test(ua)) return "Opera";
  if (/Chrome\//.test(ua) && !/Edg\//.test(ua)) return "Chrome";
  if (/Firefox\//.test(ua)) return "Firefox";
  if (/Safari\//.test(ua) && !/Chrome\//.test(ua)) return "Safari";
  return ua.slice(0, 50);
}

function AccountSection() {
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
            // Don't update local email yet — server only switches it
            // after the user clicks the link in the new mailbox.
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
      // Refresh local state with whatever the backend confirms.
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

function TintSection() {
  const { t } = useLocale();
  const [workspace, setWorkspace] = useState<Workspace>({ kind: "personal" });
  const [tint, setTint] = useState<WorkspaceTint>("default");

  useEffect(() => {
    const compute = () => {
      const w = getActiveWorkspace();
      setWorkspace(w);
      setTint(getWorkspaceTint(w));
    };
    compute();
    return subscribeWorkspace(compute);
  }, []);

  const pick = (next: WorkspaceTint) => {
    setWorkspaceTint(workspace, next);
    setTint(next);
  };

  const scopeLabel =
    workspace.kind === "team"
      ? t("settings.tint.scopeTeam", {
          name: workspace.team_name || workspace.team_id,
        })
      : t("settings.tint.scopePersonal");

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 14,
        }}
      >
        <div>
          <div className="eyebrow">{t("settings.tint.title")}</div>
          <div
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              marginTop: 4,
              lineHeight: 1.5,
            }}
          >
            {t("settings.tint.subtitle")}
          </div>
        </div>
        <div
          style={{
            fontSize: 11,
            color: "var(--text-dim)",
            textAlign: "right",
            maxWidth: 220,
          }}
        >
          {scopeLabel}
        </div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {WORKSPACE_TINTS.map((opt) => {
          const active = tint === opt;
          return (
            <button
              key={opt}
              type="button"
              onClick={() => pick(opt)}
              style={{
                padding: "8px 12px",
                fontSize: 13,
                borderRadius: 10,
                cursor: "pointer",
                border: active
                  ? "1px solid var(--accent)"
                  : "1px solid var(--border)",
                background: TINT_PREVIEW[opt],
                color: active ? "var(--accent)" : "var(--text)",
                fontWeight: active ? 600 : 500,
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: 4,
                  background: TINT_SWATCH[opt],
                  border:
                    "1px solid color-mix(in srgb, black 8%, transparent)",
                }}
              />
              {t(`settings.tint.${opt}` as const)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

const TINT_SWATCH: Record<WorkspaceTint, string> = {
  default: "#fafaf7",
  green: "#c8e1c4",
  dark: "#cfcfd6",
  orange: "#f1d2a8",
};

const TINT_PREVIEW: Record<WorkspaceTint, string> = {
  default: "var(--surface)",
  green: "linear-gradient(180deg, #f1f6f0, var(--surface))",
  dark: "linear-gradient(180deg, #ececef, var(--surface))",
  orange: "linear-gradient(180deg, #faf3ea, var(--surface))",
};

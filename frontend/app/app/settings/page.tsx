"use client";

import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  changeEmail,
  changePassword,
  connectNotion,
  disconnectHubspot,
  disconnectNotion,
  disconnectPipedrive,
  createApiKey,
  disconnectGmail,
  getGmailStatus,
  getHubspotStatus,
  getNotionStatus,
  getPipedriveStatus,
  listMyApiKeys,
  listMySessions,
  listPipedrivePipelines,
  revokeApiKey,
  setPipedriveConfig,
  startGmailAuthorize,
  startHubspotAuthorize,
  startNotionAuthorize,
  startPipedriveAuthorize,
  setNotionDatabase,
  type ApiKey,
  type ApiKeyCreated,
  type GmailIntegrationStatus,
  type HubspotIntegrationStatus,
  logoutAllSessions,
  type PipedriveIntegrationStatus,
  type PipedrivePipeline,
  revokeMySession,
  setRecoveryEmail,
  type NotionIntegrationStatus,
  type SessionInfo,
  type Webhook,
  type WebhookCreated,
  listWebhooks,
  createWebhook,
  updateWebhook,
  deleteWebhook,
  testWebhook,
  WEBHOOK_EVENT_TYPES,
} from "@/lib/api";
import { getCurrentUser, setCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";
import { ReplayTourButton } from "@/components/app/OnboardingTour";
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

        <ApiKeysSection />

        <NotionSection />

        <HubspotSection />

        <PipedriveSection />

        <GmailSection />

        <WebhooksSection />

        <TintSection />

        <HelpSection />

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
    if (!getCurrentUser()?.user_id) return;
    fetch("/api/v1/users/me", { credentials: "include" })
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

function ApiKeysSection() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draftLabel, setDraftLabel] = useState("");
  const [justCreated, setJustCreated] = useState<ApiKeyCreated | null>(null);

  const refresh = async () => {
    try {
      const r = await listMyApiKeys();
      setKeys(r.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await createApiKey(draftLabel.trim() || null);
      setJustCreated(created);
      setDraftLabel("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string) => {
    if (!confirm("Отозвать ключ? Любые скрипты, использующие его, перестанут работать.")) return;
    setBusy(true);
    try {
      await revokeApiKey(id);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        API-ключи
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: "var(--text-muted)",
          lineHeight: 1.5,
          marginBottom: 12,
        }}
      >
        Используй для скриптов / Zapier / Make. Передавай как заголовок{" "}
        <code style={{ fontFamily: "var(--font-mono)" }}>Authorization: Bearer convioo_pk_…</code>.
        Каждый ключ работает от имени этого аккаунта.
      </div>

      {justCreated && (
        <div
          style={{
            border: "1px solid var(--accent)",
            background: "var(--accent-soft)",
            borderRadius: 10,
            padding: 12,
            marginBottom: 12,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
            Скопируйте сейчас — повторно показать не сможем:
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <code
              style={{
                flex: 1,
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                padding: "6px 8px",
                background: "var(--surface)",
                borderRadius: 6,
                wordBreak: "break-all",
              }}
            >
              {justCreated.token}
            </code>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                void navigator.clipboard?.writeText(justCreated.token);
              }}
            >
              Скопировать
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setJustCreated(null)}
            >
              ОК
            </button>
          </div>
        </div>
      )}

      <form onSubmit={create} style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        <input
          className="input"
          value={draftLabel}
          onChange={(e) => setDraftLabel(e.target.value)}
          placeholder="Название ключа (например, 'Zapier')"
          style={{ flex: 1, fontSize: 13 }}
        />
        <button type="submit" className="btn btn-sm" disabled={busy}>
          {busy ? "..." : "Создать ключ"}
        </button>
      </form>

      {error && <div style={{ fontSize: 13, color: "var(--cold)", marginBottom: 8 }}>{error}</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {keys === null ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
        ) : keys.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Пока ни одного ключа.
          </div>
        ) : (
          keys.map((k) => (
            <div
              key={k.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 10,
                padding: 12,
                display: "flex",
                gap: 12,
                alignItems: "center",
                opacity: k.revoked ? 0.5 : 1,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>
                  {k.label ?? "Без названия"}
                  {k.revoked && (
                    <span
                      style={{
                        marginLeft: 8,
                        fontSize: 10,
                        color: "var(--cold)",
                        textTransform: "uppercase",
                        letterSpacing: 0.5,
                      }}
                    >
                      отозван
                    </span>
                  )}
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                    color: "var(--text-muted)",
                  }}
                >
                  {k.token_preview} · {k.last_used_at ? `последнее использование ${new Date(k.last_used_at).toLocaleDateString()}` : "никогда не использовался"}
                </div>
              </div>
              {!k.revoked && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => void revoke(k.id)}
                  style={{ color: "var(--cold)" }}
                  disabled={busy}
                >
                  Отозвать
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function NotionSection() {
  const [status, setStatus] = useState<NotionIntegrationStatus | null>(null);
  const [showTokenForm, setShowTokenForm] = useState(false);
  const [showDbForm, setShowDbForm] = useState(false);
  const [token, setToken] = useState("");
  const [databaseId, setDatabaseId] = useState("");
  const [dbDraft, setDbDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const emptyStatus: NotionIntegrationStatus = {
    connected: false,
    token_preview: null,
    database_id: null,
    workspace_name: null,
    owner_email: null,
    auth_type: null,
    updated_at: null,
  };

  useEffect(() => {
    let cancelled = false;
    getNotionStatus()
      .then((s) => {
        if (!cancelled) {
          setStatus(s);
          // After OAuth callback redirect we arrive with ?notion=connected
          // Show the DB form automatically if token is saved but no DB yet.
          if (s.connected && !s.database_id) setShowDbForm(true);
        }
      })
      .catch(() => {
        if (!cancelled) setStatus(emptyStatus);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Handle ?notion=connected (set by the OAuth callback redirect).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("notion") === "connected") {
      // Clean up the URL without reloading.
      const url = new URL(window.location.href);
      url.searchParams.delete("notion");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  const connectOAuth = async () => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await startNotionAuthorize();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const submitInternalToken = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!token.trim() || !databaseId.trim()) return;
    setBusy(true);
    try {
      const next = await connectNotion({
        token: token.trim(),
        databaseId: databaseId.trim(),
      });
      setStatus(next);
      setShowTokenForm(false);
      setToken("");
      setDatabaseId("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const submitDatabase = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!dbDraft.trim()) return;
    setBusy(true);
    try {
      const next = await setNotionDatabase(dbDraft.trim());
      setStatus(next);
      setShowDbForm(false);
      setDbDraft("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm("Отключить Notion? Сохранённый токен будет удалён.")) return;
    setBusy(true);
    setError(null);
    try {
      await disconnectNotion();
      setStatus(emptyStatus);
      setShowDbForm(false);
      setShowTokenForm(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Интеграция: Notion
      </div>

      {status === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
      ) : status.connected ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 16,
              justifyContent: "space-between",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                {status.workspace_name ?? "Notion подключён"}
                {status.auth_type === "oauth" && (
                  <span
                    className="chip"
                    style={{
                      marginLeft: 8,
                      fontSize: 10,
                      padding: "2px 6px",
                      background: "var(--accent-soft)",
                      color: "var(--accent)",
                    }}
                  >
                    OAuth
                  </span>
                )}
              </div>
              <div style={{ fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.6 }}>
                {status.owner_email && (
                  <>Аккаунт: {status.owner_email}<br /></>
                )}
                Database ID:{" "}
                <span style={{ fontFamily: "var(--font-mono)" }}>
                  {status.database_id ?? <em style={{ color: "var(--cold)" }}>не задан</em>}
                </span>
              </div>
              {!status.database_id && (
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--cold)",
                    marginTop: 4,
                    lineHeight: 1.5,
                  }}
                >
                  Укажите Database ID чтобы начать экспорт лидов.
                </div>
              )}
              <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 6 }}>
                Лиды экспортируются как страницы в эту базу. Колонки
                мапятся по имени (Name, Score, Status и т.д.).
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setShowDbForm((v) => !v);
                  setShowTokenForm(false);
                  setError(null);
                  setDbDraft(status.database_id ?? "");
                }}
                disabled={busy}
              >
                {status.database_id ? "Сменить базу" : "Задать базу"}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => void disconnect()}
                disabled={busy}
                style={{ color: "var(--cold)" }}
              >
                Отключить
              </button>
            </div>
          </div>

          {showDbForm && (
            <form
              onSubmit={submitDatabase}
              style={{ display: "flex", flexDirection: "column", gap: 10 }}
            >
              <div style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5 }}>
                Откройте нужную базу в Notion, скопируйте 32-значный ID из URL
                (часть после последнего «/» до «?»). Убедитесь что{" "}
                {status.auth_type === "oauth"
                  ? "Convioo имеет доступ к этой базе"
                  : "интеграция share-нута на эту базу"}
                .
              </div>
              <input
                className="input"
                value={dbDraft}
                onChange={(e) => setDbDraft(e.target.value)}
                placeholder="Database ID (32 hex)"
                autoFocus
              />
              {error && (
                <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>
              )}
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="submit"
                  className="btn btn-sm"
                  disabled={busy || !dbDraft.trim()}
                >
                  {busy ? "Проверяю…" : "Сохранить"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setShowDbForm(false);
                    setError(null);
                  }}
                >
                  Отмена
                </button>
              </div>
            </form>
          )}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <p style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5, margin: 0 }}>
            Подключите Notion чтобы экспортировать лидов прямо в вашу базу
            данных одним кликом. Выберите удобный способ подключения.
          </p>

          {!showTokenForm ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => void connectOAuth()}
                disabled={busy}
                style={{ alignSelf: "flex-start" }}
              >
                {busy ? "..." : "Подключить через Notion OAuth"}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowTokenForm(true)}
                style={{ alignSelf: "flex-start", fontSize: 12 }}
              >
                Использовать internal integration token
              </button>
            </div>
          ) : (
            <form
              onSubmit={submitInternalToken}
              style={{ display: "flex", flexDirection: "column", gap: 10 }}
            >
              <p style={{ fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.5, margin: 0 }}>
                1. Создайте интеграцию на{" "}
                <a
                  href="https://www.notion.so/my-integrations"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: "var(--accent)" }}
                >
                  notion.so/my-integrations
                </a>
                , скопируйте Internal Integration Token.
                <br />
                2. Share → пригласите интеграцию к нужной базе.
                <br />
                3. Скопируйте Database ID из URL базы.
              </p>
              <input
                className="input"
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="ntn_•••••••••••••"
                autoComplete="off"
              />
              <input
                className="input"
                value={databaseId}
                onChange={(e) => setDatabaseId(e.target.value)}
                placeholder="Database ID (32 hex)"
              />
              {error && (
                <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>
              )}
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="submit"
                  className="btn btn-sm"
                  disabled={busy || !token.trim() || !databaseId.trim()}
                >
                  {busy ? "Проверяю доступ…" : "Подключить"}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setShowTokenForm(false);
                    setError(null);
                  }}
                >
                  Назад
                </button>
              </div>
            </form>
          )}

          {error && !showTokenForm && (
            <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>
          )}
        </div>
      )}
    </div>
  );
}

function WebhooksSection() {
  const [webhooks, setWebhooks] = useState<Webhook[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [justCreated, setJustCreated] = useState<WebhookCreated | null>(null);

  const [newUrl, setNewUrl] = useState("");
  const [newEvents, setNewEvents] = useState<string[]>([]);
  const [newDesc, setNewDesc] = useState("");

  const refresh = async () => {
    try {
      const r = await listWebhooks();
      setWebhooks(r.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newUrl.trim() || newEvents.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createWebhook({
        targetUrl: newUrl.trim(),
        eventTypes: newEvents,
        description: newDesc.trim() || undefined,
      });
      setJustCreated(created);
      setShowCreate(false);
      setNewUrl("");
      setNewEvents([]);
      setNewDesc("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (wh: Webhook) => {
    setBusy(true);
    try {
      await updateWebhook(wh.id, { active: !wh.active });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const remove = async (wh: Webhook) => {
    if (!confirm(`Удалить webhook ${wh.target_url}?`)) return;
    setBusy(true);
    try {
      await deleteWebhook(wh.id);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const test = async (wh: Webhook) => {
    setBusy(true);
    try {
      await testWebhook(wh.id);
      alert(`Ping отправлен на ${wh.target_url}`);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleEvent = (ev: string) => {
    setNewEvents((prev) =>
      prev.includes(ev) ? prev.filter((x) => x !== ev) : [...prev, ev],
    );
  };

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
        <div className="eyebrow">Webhooks</div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => {
            setShowCreate((v) => !v);
            setError(null);
          }}
        >
          {showCreate ? "Отмена" : "+ Добавить"}
        </button>
      </div>

      <div
        style={{
          fontSize: 12.5,
          color: "var(--text-muted)",
          lineHeight: 1.5,
          marginBottom: 12,
        }}
      >
        Convioo отправляет POST-запросы с HMAC-подписью на ваш URL при
        наступлении выбранных событий. Заголовок{" "}
        <code style={{ fontFamily: "var(--font-mono)" }}>
          X-Convioo-Signature
        </code>{" "}
        содержит{" "}
        <code style={{ fontFamily: "var(--font-mono)" }}>sha256=HMAC</code>.
        Подробнее на{" "}
        <a href="/developers" style={{ color: "var(--accent)" }}>
          /developers
        </a>
        .
      </div>

      {justCreated && (
        <div
          style={{
            border: "1px solid var(--accent)",
            background: "var(--accent-soft)",
            borderRadius: 10,
            padding: 12,
            marginBottom: 12,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
            Скопируйте секрет — повторно показать не сможем:
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <code
              style={{
                flex: 1,
                fontFamily: "var(--font-mono)",
                fontSize: 11.5,
                padding: "6px 8px",
                background: "var(--surface)",
                borderRadius: 6,
                wordBreak: "break-all",
              }}
            >
              {justCreated.secret}
            </code>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() =>
                void navigator.clipboard?.writeText(justCreated.secret)
              }
            >
              Скопировать
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setJustCreated(null)}
            >
              ОК
            </button>
          </div>
        </div>
      )}

      {showCreate && (
        <form
          onSubmit={create}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 10,
            padding: 14,
            border: "1px solid var(--border)",
            borderRadius: 12,
            marginBottom: 14,
            background: "var(--surface-2)",
          }}
        >
          <div className="eyebrow" style={{ fontSize: 11, marginBottom: 2 }}>
            Новый webhook
          </div>
          <input
            className="input"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            placeholder="https://your-server.com/hooks/convioo"
            style={{ fontSize: 13 }}
          />
          <input
            className="input"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder="Описание (необязательно)"
            style={{ fontSize: 13 }}
          />
          <div>
            <div
              className="eyebrow"
              style={{ fontSize: 11, marginBottom: 8 }}
            >
              События
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {WEBHOOK_EVENT_TYPES.map((ev) => (
                <label
                  key={ev}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    fontSize: 12.5,
                    cursor: "pointer",
                    padding: "5px 10px",
                    border: `1px solid ${newEvents.includes(ev) ? "var(--accent)" : "var(--border)"}`,
                    borderRadius: 8,
                    background: newEvents.includes(ev)
                      ? "var(--accent-soft)"
                      : "transparent",
                    color: newEvents.includes(ev)
                      ? "var(--accent)"
                      : "var(--text-muted)",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={newEvents.includes(ev)}
                    onChange={() => toggleEvent(ev)}
                    style={{ display: "none" }}
                  />
                  <code style={{ fontFamily: "var(--font-mono)" }}>{ev}</code>
                </label>
              ))}
            </div>
          </div>
          {error && (
            <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="submit"
              className="btn btn-sm"
              disabled={busy || !newUrl.trim() || newEvents.length === 0}
            >
              {busy ? "..." : "Создать"}
            </button>
          </div>
        </form>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {webhooks === null ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Загрузка…
          </div>
        ) : webhooks.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Нет активных webhooks.
          </div>
        ) : (
          webhooks.map((wh) => (
            <div
              key={wh.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 10,
                padding: 12,
                opacity: wh.active ? 1 : 0.6,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 10,
                  alignItems: "flex-start",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 12.5,
                      fontWeight: 600,
                      wordBreak: "break-all",
                    }}
                  >
                    {wh.target_url}
                    {!wh.active && (
                      <span
                        style={{
                          marginLeft: 8,
                          fontSize: 10,
                          color: "var(--cold)",
                          textTransform: "uppercase",
                          letterSpacing: 0.5,
                          fontFamily: "inherit",
                        }}
                      >
                        отключён
                      </span>
                    )}
                  </div>
                  <div
                    style={{
                      fontSize: 11.5,
                      color: "var(--text-muted)",
                      marginTop: 4,
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 4,
                    }}
                  >
                    {wh.event_types.map((ev) => (
                      <span
                        key={ev}
                        className="chip"
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: 10,
                          padding: "2px 6px",
                        }}
                      >
                        {ev}
                      </span>
                    ))}
                  </div>
                  {wh.description && (
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--text-dim)",
                        marginTop: 4,
                      }}
                    >
                      {wh.description}
                    </div>
                  )}
                  <div
                    style={{
                      fontSize: 11.5,
                      color: "var(--text-dim)",
                      marginTop: 4,
                    }}
                  >
                    Секрет:{" "}
                    <span style={{ fontFamily: "var(--font-mono)" }}>
                      {wh.secret_preview}
                    </span>
                    {wh.last_delivery_at && (
                      <>
                        {" · "}
                        последняя доставка:{" "}
                        {new Date(wh.last_delivery_at).toLocaleString()}{" "}
                        {wh.last_delivery_status && (
                          <span
                            style={{
                              color:
                                wh.last_delivery_status < 300
                                  ? "var(--hot)"
                                  : "var(--cold)",
                            }}
                          >
                            {wh.last_delivery_status}
                          </span>
                        )}
                      </>
                    )}
                    {wh.failure_count > 0 && (
                      <span style={{ color: "var(--cold)" }}>
                        {" · "}{wh.failure_count} ошибок подряд
                      </span>
                    )}
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: 6,
                    flexShrink: 0,
                    flexWrap: "wrap",
                    justifyContent: "flex-end",
                  }}
                >
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void test(wh)}
                    disabled={busy}
                    title="Отправить тестовый ping"
                  >
                    Тест
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void toggleActive(wh)}
                    disabled={busy}
                  >
                    {wh.active ? "Отключить" : "Включить"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void remove(wh)}
                    disabled={busy}
                    style={{ color: "var(--cold)" }}
                  >
                    Удалить
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
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

function GmailSection() {
  const [status, setStatus] = useState<GmailIntegrationStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getGmailStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled)
          setStatus({
            connected: false,
            account_email: null,
            scope: null,
            expires_at: null,
          });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await startGmailAuthorize();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm("Отключить Gmail? Сохранённые токены будут удалены.")) return;
    setBusy(true);
    setError(null);
    try {
      await disconnectGmail();
      setStatus({
        connected: false,
        account_email: null,
        scope: null,
        expires_at: null,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Интеграция: Gmail
      </div>

      {status === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
      ) : status.connected ? (
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 16,
            justifyContent: "space-between",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Подключено как {status.account_email ?? "—"}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              Доступ ограничен скоупом ``gmail.send`` — мы можем отправлять
              письма от вашего имени, но не читать почту.
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void disconnect()}
            disabled={busy}
            style={{ color: "var(--cold)" }}
          >
            Отключить
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            Подключите Gmail чтобы отправлять холодные письма прямо из
            карточки лида. Конвиу запросит только право на отправку
            писем — почта остаётся приватной.
          </p>
          <div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void connect()}
              disabled={busy}
            >
              {busy ? "..." : "Подключить Gmail"}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: 12,
            fontSize: 12.5,
            color: "var(--cold)",
            lineHeight: 1.5,
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}

function HelpSection() {
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Помощь
      </div>
      <div
        style={{
          fontSize: 13.5,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 12,
        }}
      >
        Запустите 4-шаговый тур заново, если хочется ещё раз пройтись
        по основным экранам.
      </div>
      <ReplayTourButton className="btn btn-ghost btn-sm">
        Пройти тур заново
      </ReplayTourButton>
    </div>
  );
}

function HubspotSection() {
  const [status, setStatus] = useState<HubspotIntegrationStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getHubspotStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled)
          setStatus({
            connected: false,
            portal_id: null,
            account_email: null,
            scope: null,
            expires_at: null,
          });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await startHubspotAuthorize();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm("Отключить HubSpot? Сохранённые токены будут удалены.")) return;
    setBusy(true);
    setError(null);
    try {
      await disconnectHubspot();
      setStatus({
        connected: false,
        portal_id: null,
        account_email: null,
        scope: null,
        expires_at: null,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Интеграция: HubSpot
      </div>

      {status === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Загрузка…</div>
      ) : status.connected ? (
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 16,
            justifyContent: "space-between",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Подключено
              {status.account_email ? ` (${status.account_email})` : ""}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              Portal ID:{" "}
              <span style={{ fontFamily: "var(--font-mono)" }}>
                {status.portal_id ?? "—"}
              </span>
              <br />
              Скоупы: contacts.write + contacts.read.
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void disconnect()}
            disabled={busy}
            style={{ color: "var(--cold)" }}
          >
            Отключить
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            Подключите HubSpot чтобы экспортировать выбранных лидов
            прямо в ваш CRM-портал. Конвиу пишет только в Contacts —
            никаких изменений в сделках, компаниях или заметках.
          </p>
          <div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void connect()}
              disabled={busy}
            >
              {busy ? "..." : "Подключить HubSpot"}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: 12,
            fontSize: 12.5,
            color: "var(--cold)",
            lineHeight: 1.5,
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}

function PipedriveSection() {
  const [status, setStatus] = useState<PipedriveIntegrationStatus | null>(
    null,
  );
  const [pipelines, setPipelines] = useState<PipedrivePipeline[] | null>(
    null,
  );
  const [pipelineId, setPipelineId] = useState<number | null>(null);
  const [stageId, setStageId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPipedriveStatus()
      .then((s) => {
        if (cancelled) return;
        setStatus(s);
        setPipelineId(s.default_pipeline_id);
        setStageId(s.default_stage_id);
      })
      .catch(() => {
        if (cancelled) return;
        setStatus({
          connected: false,
          api_domain: null,
          account_email: null,
          scope: null,
          expires_at: null,
          default_pipeline_id: null,
          default_stage_id: null,
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!status?.connected || pipelines !== null) return;
    let cancelled = false;
    listPipedrivePipelines()
      .then((r) => {
        if (cancelled) return;
        setPipelines(r.items);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : String(e));
        setPipelines([]);
      });
    return () => {
      cancelled = true;
    };
  }, [status?.connected, pipelines]);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await startPipedriveAuthorize();
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm("Отключить Pipedrive? Сохранённые токены будут удалены."))
      return;
    setBusy(true);
    setError(null);
    try {
      await disconnectPipedrive();
      setStatus({
        connected: false,
        api_domain: null,
        account_email: null,
        scope: null,
        expires_at: null,
        default_pipeline_id: null,
        default_stage_id: null,
      });
      setPipelines(null);
      setPipelineId(null);
      setStageId(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const saveConfig = async () => {
    if (!pipelineId || !stageId) return;
    setBusy(true);
    setError(null);
    try {
      const next = await setPipedriveConfig({
        defaultPipelineId: pipelineId,
        defaultStageId: stageId,
      });
      setStatus(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const stagesForPipeline =
    pipelines?.find((p) => p.id === pipelineId)?.stages ?? [];

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Интеграция: Pipedrive
      </div>

      {status === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          Загрузка…
        </div>
      ) : status.connected ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 16,
              justifyContent: "space-between",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}
              >
                Подключено
                {status.account_email ? ` (${status.account_email})` : ""}
              </div>
              <div
                style={{
                  fontSize: 12.5,
                  color: "var(--text-muted)",
                  lineHeight: 1.5,
                }}
              >
                API:{" "}
                <span style={{ fontFamily: "var(--font-mono)" }}>
                  {status.api_domain ?? "—"}
                </span>
              </div>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => void disconnect()}
              disabled={busy}
              style={{ color: "var(--cold)" }}
            >
              Отключить
            </button>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="eyebrow" style={{ fontSize: 11 }}>
              Куда складывать новые сделки
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <select
                className="input"
                style={{ flex: 1, minWidth: 180 }}
                value={pipelineId ?? ""}
                onChange={(e) => {
                  const v = e.target.value
                    ? Number(e.target.value)
                    : null;
                  setPipelineId(v);
                  setStageId(null);
                }}
                disabled={busy || pipelines === null}
              >
                <option value="">Pipeline…</option>
                {(pipelines ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <select
                className="input"
                style={{ flex: 1, minWidth: 180 }}
                value={stageId ?? ""}
                onChange={(e) =>
                  setStageId(e.target.value ? Number(e.target.value) : null)
                }
                disabled={busy || !pipelineId}
              >
                <option value="">Stage…</option>
                {stagesForPipeline.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => void saveConfig()}
                disabled={busy || !pipelineId || !stageId}
              >
                Сохранить
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            Подключите Pipedrive чтобы экспортировать выбранных лидов
            как Person + Deal в выбранный pipeline. Конвиу пишет только
            в Persons и Deals — никаких изменений в существующих
            организациях или активностях.
          </p>
          <div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void connect()}
              disabled={busy}
            >
              {busy ? "..." : "Подключить Pipedrive"}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: 12,
            fontSize: 12.5,
            color: "var(--cold)",
            lineHeight: 1.5,
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}

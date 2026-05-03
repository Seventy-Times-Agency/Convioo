"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  listMySessions,
  logoutAllSessions,
  revokeMySession,
  setRecoveryEmail,
  type SessionInfo,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";

export function SecuritySection() {
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
      // best effort
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
  if (/Edg\//.test(ua)) return "Edge";
  if (/OPR\//.test(ua)) return "Opera";
  if (/Chrome\//.test(ua) && !/Edg\//.test(ua)) return "Chrome";
  if (/Firefox\//.test(ua)) return "Firefox";
  if (/Safari\//.test(ua) && !/Chrome\//.test(ua)) return "Safari";
  return ua.slice(0, 50);
}

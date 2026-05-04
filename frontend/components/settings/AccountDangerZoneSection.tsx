"use client";

import { useEffect, useState } from "react";
import { deleteAccount, gdprExportUrl, getMyProfile } from "@/lib/api";
import { clearCurrentUser } from "@/lib/auth";

export function AccountDangerZoneSection() {
  const [email, setEmail] = useState<string | null>(null);
  const [confirmEmail, setConfirmEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [showDelete, setShowDelete] = useState(false);

  useEffect(() => {
    void getMyProfile()
      .then((p) => setEmail(p.email ?? null))
      .catch(() => setEmail(null));
  }, []);

  const downloadExport = () => {
    setError(null);
    setInfo("Готовим архив с твоими данными…");
    // Same-origin link, cookie auth attaches automatically.
    window.location.href = gdprExportUrl();
  };

  const submitDelete = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!email) {
      setError("Не удалось определить email аккаунта.");
      return;
    }
    if (confirmEmail.trim().toLowerCase() !== email.toLowerCase()) {
      setError("Введённый email не совпадает с email аккаунта.");
      return;
    }
    if (
      !confirm(
        "Удалить аккаунт навсегда? Это действие необратимо: все поиски, лиды, шаблоны и интеграции будут стёрты.",
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      await deleteAccount({
        confirmEmail: confirmEmail.trim(),
        password: password || undefined,
      });
      clearCurrentUser();
      window.location.href = "/";
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Данные и аккаунт
      </div>

      <div style={{ marginBottom: 22 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>
          Экспорт данных (GDPR)
        </div>
        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-muted)",
            lineHeight: 1.5,
            marginBottom: 10,
          }}
        >
          Скачай ZIP со всем что мы храним о тебе: профиль, поиски, лиды,
          шаблоны, активность, аудит-лог. Содержимое — машиночитаемый JSON
          + CSV.
        </div>
        <button
          type="button"
          className="btn btn-sm"
          onClick={downloadExport}
          disabled={busy}
        >
          Скачать архив
        </button>
        {info && (
          <div
            style={{
              fontSize: 12.5,
              color: "var(--text-muted)",
              marginTop: 8,
            }}
          >
            {info}
          </div>
        )}
      </div>

      <div
        style={{
          borderTop: "1px solid var(--border)",
          paddingTop: 18,
        }}
      >
        <div
          style={{
            fontSize: 13.5,
            fontWeight: 600,
            marginBottom: 6,
            color: "var(--cold)",
          }}
        >
          Удалить аккаунт
        </div>
        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-muted)",
            lineHeight: 1.5,
            marginBottom: 10,
          }}
        >
          Удаление необратимо. Все поиски, лиды, шаблоны, интеграции и
          OAuth-токены будут стёрты сразу. Если ты владелец команды —
          сначала передай владение или удали команду.
        </div>

        {!showDelete ? (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            style={{ color: "var(--cold)" }}
            onClick={() => setShowDelete(true)}
          >
            Я хочу удалить аккаунт
          </button>
        ) : (
          <form
            onSubmit={submitDelete}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
              maxWidth: 420,
            }}
          >
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Чтобы подтвердить, введи свой email{email ? ` (${email})` : ""} и
              пароль.
            </div>
            <input
              className="input"
              type="email"
              placeholder="email аккаунта"
              value={confirmEmail}
              onChange={(e) => setConfirmEmail(e.target.value)}
              autoComplete="off"
              style={{ fontSize: 13 }}
            />
            <input
              className="input"
              type="password"
              placeholder="пароль (если задан)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              style={{ fontSize: 13 }}
            />
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="submit"
                className="btn btn-sm"
                disabled={busy}
                style={{
                  background: "var(--cold)",
                  color: "#fff",
                  border: "none",
                }}
              >
                {busy ? "Удаление…" : "Удалить навсегда"}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setShowDelete(false);
                  setConfirmEmail("");
                  setPassword("");
                  setError(null);
                }}
                disabled={busy}
              >
                Отмена
              </button>
            </div>
            {error && (
              <div style={{ fontSize: 12.5, color: "var(--cold)" }}>{error}</div>
            )}
          </form>
        )}
      </div>
    </div>
  );
}

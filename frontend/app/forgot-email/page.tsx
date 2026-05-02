"use client";

import { useState } from "react";
import Link from "next/link";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { ApiError, forgotEmail } from "@/lib/api";

export default function ForgotEmailPage() {
  const [recovery, setRecovery] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!recovery.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      await forgotEmail(recovery.trim().toLowerCase());
      setDone(true);
    } catch (e) {
      const detail =
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(detail);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell title="Восстановление email">
      {done ? (
        <div>
          <p style={{ color: "var(--text-muted)", lineHeight: 1.55, fontSize: 15 }}>
            Если этот резервный email привязан к аккаунту, мы отправили
            на него письмо с напоминанием основного email и ссылкой на
            смену.
          </p>
          <p style={{ marginTop: 18, fontSize: 13 }}>
            <Link href="/login" style={{ color: "var(--accent)", fontWeight: 600 }}>
              ← Вернуться ко входу
            </Link>
          </p>
        </div>
      ) : (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <p style={{ color: "var(--text-muted)", marginBottom: 6, fontSize: 14, lineHeight: 1.55 }}>
            Если вы добавили резервный email в настройках аккаунта,
            введите его здесь — мы отправим на него напоминание о
            привязанном основном адресе и ссылку для смены.
          </p>
          <Field label="Резервный email">
            <input
              className="input"
              type="email"
              value={recovery}
              onChange={(e) => setRecovery(e.target.value)}
              placeholder="[email protected]"
              autoFocus
              autoComplete="email"
            />
          </Field>
          {error && <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>}
          <button
            type="submit"
            className="btn btn-lg"
            disabled={submitting || !recovery.trim()}
            style={{ justifyContent: "center", marginTop: 6 }}
          >
            {submitting ? "Отправляем…" : "Отправить напоминание"}{" "}
            <Icon name="arrow" size={15} />
          </button>
          <div style={{ marginTop: 14, fontSize: 13, color: "var(--text-muted)" }}>
            <Link href="/login" style={{ color: "var(--accent)", fontWeight: 600 }}>
              ← Вернуться ко входу
            </Link>
            {"  ·  "}
            <Link href="/forgot-password" style={{ color: "var(--accent)", fontWeight: 600 }}>
              Забыли пароль?
            </Link>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
            Не помните и резервный email? Напишите нам на{" "}
            <a href="mailto:[email protected]" style={{ color: "var(--accent)" }}>
              [email protected]
            </a>{" "}
            — мы поможем вернуть доступ вручную.
          </p>
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

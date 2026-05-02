"use client";

import { useState } from "react";
import Link from "next/link";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { ApiError, forgotPassword } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      await forgotPassword(email.trim().toLowerCase());
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
    <AuthShell title="Сброс пароля">
      {done ? (
        <div>
          <p style={{ color: "var(--text-muted)", lineHeight: 1.55, fontSize: 15 }}>
            Если такой аккаунт существует, мы отправили письмо со ссылкой
            на сброс пароля. Проверьте почту — ссылка действует 1 час.
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
            Введите email от вашего аккаунта Convioo. Мы вышлем ссылку для
            создания нового пароля.
          </p>
          <Field label="Email">
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="[email protected]"
              autoFocus
              autoComplete="email"
            />
          </Field>
          {error && <div style={{ fontSize: 13, color: "var(--cold)" }}>{error}</div>}
          <button
            type="submit"
            className="btn btn-lg"
            disabled={submitting || !email.trim()}
            style={{ justifyContent: "center", marginTop: 6 }}
          >
            {submitting ? "Отправляем…" : "Отправить ссылку"} <Icon name="arrow" size={15} />
          </button>
          <div style={{ marginTop: 14, fontSize: 13, color: "var(--text-muted)" }}>
            <Link href="/login" style={{ color: "var(--accent)", fontWeight: 600 }}>
              ← Вернуться ко входу
            </Link>
            {"  ·  "}
            <Link href="/forgot-email" style={{ color: "var(--accent)", fontWeight: 600 }}>
              Забыли email?
            </Link>
          </div>
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

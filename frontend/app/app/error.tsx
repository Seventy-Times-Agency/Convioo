"use client";

import { useEffect } from "react";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[app error boundary]", error);
  }, [error]);

  return (
    <main
      style={{
        minHeight: "calc(100vh - 64px)",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <div style={{ maxWidth: 520, textAlign: "center" }}>
        <h1 style={{ fontSize: 22, marginBottom: 8 }}>
          Этот раздел временно недоступен
        </h1>
        <p style={{ marginBottom: 16, opacity: 0.72 }}>
          Произошла ошибка при загрузке. Попробуйте ещё раз — если повторится,
          напишите в поддержку, и мы посмотрим логи.
        </p>
        {error.digest ? (
          <p style={{ fontSize: 12, opacity: 0.5, marginBottom: 16 }}>
            id: {error.digest}
          </p>
        ) : null}
        <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
          <button
            onClick={() => reset()}
            style={{
              padding: "10px 16px",
              borderRadius: 8,
              border: "1px solid currentColor",
              background: "transparent",
              cursor: "pointer",
            }}
          >
            Повторить
          </button>
          <a
            href="/app"
            style={{
              padding: "10px 16px",
              borderRadius: 8,
              border: "1px solid currentColor",
              textDecoration: "none",
              color: "inherit",
            }}
          >
            В CRM
          </a>
        </div>
      </div>
    </main>
  );
}

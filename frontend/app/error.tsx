"use client";

import { useEffect } from "react";

export default function PublicError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[public error boundary]", error);
  }, [error]);

  return (
    <main
      style={{
        minHeight: "60vh",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <div style={{ maxWidth: 480, textAlign: "center" }}>
        <h1 style={{ fontSize: 22, marginBottom: 8 }}>Ошибка страницы</h1>
        <p style={{ marginBottom: 16, opacity: 0.72 }}>
          Не удалось отрисовать эту страницу. Можно повторить попытку или
          вернуться на главную.
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
            href="/"
            style={{
              padding: "10px 16px",
              borderRadius: 8,
              border: "1px solid currentColor",
              textDecoration: "none",
              color: "inherit",
            }}
          >
            На главную
          </a>
        </div>
      </div>
    </main>
  );
}

"use client";

import { useEffect } from "react";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[root error boundary]", error);
  }, [error]);

  return (
    <html lang="ru">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          fontFamily:
            "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
          background: "#FAFAF7",
          color: "#0F0F11",
        }}
      >
        <div style={{ maxWidth: 480, padding: 24, textAlign: "center" }}>
          <h1 style={{ fontSize: 22, marginBottom: 8 }}>
            Что-то пошло не так
          </h1>
          <p style={{ marginBottom: 16, opacity: 0.72 }}>
            Мы записали ошибку. Попробуйте перезагрузить страницу или
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
                border: "1px solid #0F0F11",
                borderRadius: 8,
                background: "#0F0F11",
                color: "#FAFAF7",
                cursor: "pointer",
              }}
            >
              Повторить
            </button>
            <a
              href="/"
              style={{
                padding: "10px 16px",
                border: "1px solid #0F0F11",
                borderRadius: 8,
                color: "#0F0F11",
                textDecoration: "none",
              }}
            >
              На главную
            </a>
          </div>
        </div>
      </body>
    </html>
  );
}

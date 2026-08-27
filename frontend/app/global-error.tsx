"use client";

import { useEffect, useState } from "react";
import { readUiLang, pickUiLang, type UiLang } from "@/lib/uiLang";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const [lang, setLang] = useState<UiLang>("ru");

  useEffect(() => {
    setLang(readUiLang());
    // eslint-disable-next-line no-console
    console.error("[root error boundary]", error);
  }, [error]);

  const title = pickUiLang(lang, {
    ru: "Что-то пошло не так",
    uk: "Щось пішло не так",
    en: "Something went wrong",
  });
  const body = pickUiLang(lang, {
    ru: "Мы записали ошибку. Попробуйте перезагрузить страницу или вернуться на главную.",
    uk: "Ми зафіксували помилку. Спробуйте перезавантажити сторінку або повернутися на головну.",
    en: "We've logged the error. Try reloading the page or returning to the home page.",
  });
  const retry = pickUiLang(lang, { ru: "Повторить", uk: "Повторити", en: "Try again" });
  const home = pickUiLang(lang, { ru: "На главную", uk: "На головну", en: "Go home" });

  return (
    <html lang={lang}>
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          fontFamily:
            "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
          background: "#08060F",
          color: "#F0EDFA",
        }}
      >
        <div style={{ maxWidth: 480, padding: 24, textAlign: "center" }}>
          <h1 style={{ fontSize: 22, marginBottom: 8 }}>{title}</h1>
          <p style={{ marginBottom: 16, opacity: 0.72 }}>{body}</p>
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
                border: "1px solid transparent",
                borderRadius: 8,
                background: "linear-gradient(100deg, #8B5CF6, #22D3EE)",
                color: "#fff",
                cursor: "pointer",
              }}
            >
              {retry}
            </button>
            <a
              href="/"
              style={{
                padding: "10px 16px",
                border: "1px solid #362A51",
                borderRadius: 8,
                color: "#F0EDFA",
                textDecoration: "none",
              }}
            >
              {home}
            </a>
          </div>
        </div>
      </body>
    </html>
  );
}

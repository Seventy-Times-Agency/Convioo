"use client";

import { useEffect, useState } from "react";
import { readUiLang, pickUiLang, type UiLang } from "@/lib/uiLang";

export default function PublicError({
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
    console.error("[public error boundary]", error);
  }, [error]);

  const title = pickUiLang(lang, {
    ru: "Ошибка страницы",
    uk: "Помилка сторінки",
    en: "Page error",
  });
  const body = pickUiLang(lang, {
    ru: "Не удалось отрисовать эту страницу. Можно повторить попытку или вернуться на главную.",
    uk: "Не вдалося відобразити цю сторінку. Можна повторити спробу або повернутися на головну.",
    en: "We couldn't render this page. Try again or return to the home page.",
  });
  const retry = pickUiLang(lang, { ru: "Повторить", uk: "Повторити", en: "Try again" });
  const home = pickUiLang(lang, {
    ru: "На главную",
    uk: "На головну",
    en: "Go home",
  });

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
              borderRadius: 8,
              border: "1px solid currentColor",
              background: "transparent",
              cursor: "pointer",
            }}
          >
            {retry}
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
            {home}
          </a>
        </div>
      </div>
    </main>
  );
}

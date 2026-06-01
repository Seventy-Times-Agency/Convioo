"use client";

import { useEffect, useState } from "react";
import { readUiLang, pickUiLang, type UiLang } from "@/lib/uiLang";

export default function AppError({
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
    console.error("[app error boundary]", error);
  }, [error]);

  const title = pickUiLang(lang, {
    ru: "Этот раздел временно недоступен",
    uk: "Цей розділ тимчасово недоступний",
    en: "This section is temporarily unavailable",
  });
  const body = pickUiLang(lang, {
    ru: "Произошла ошибка при загрузке. Попробуйте ещё раз — если повторится, напишите в поддержку, и мы посмотрим логи.",
    uk: "Сталася помилка під час завантаження. Спробуйте ще раз — якщо повториться, напишіть у підтримку, і ми перевіримо логи.",
    en: "Something went wrong while loading. Try again — if it keeps happening, contact support and we'll check the logs.",
  });
  const retry = pickUiLang(lang, { ru: "Повторить", uk: "Повторити", en: "Try again" });
  const toCrm = pickUiLang(lang, { ru: "В CRM", uk: "До CRM", en: "Back to CRM" });

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
            href="/app"
            style={{
              padding: "10px 16px",
              borderRadius: 8,
              border: "1px solid currentColor",
              textDecoration: "none",
              color: "inherit",
            }}
          >
            {toCrm}
          </a>
        </div>
      </div>
    </main>
  );
}

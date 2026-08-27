"use client";

import { useLocale, type Locale } from "@/lib/i18n";

/**
 * Small segmented-control RU/UK/EN toggle. Persists via the i18n provider.
 */
export function LanguageSwitcher({
  compact = false,
}: {
  compact?: boolean;
}) {
  const { lang, setLang } = useLocale();
  const opts: Locale[] = ["ru", "uk", "en"];
  return (
    <div
      className="seg"
      style={{
        padding: 2,
        fontSize: compact ? 11 : 12,
      }}
    >
      {opts.map((o) => (
        <button
          key={o}
          type="button"
          className={lang === o ? "active" : ""}
          onClick={() => setLang(o)}
          style={{
            padding: compact ? "3px 8px" : "4px 10px",
            fontSize: compact ? 11 : 12,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

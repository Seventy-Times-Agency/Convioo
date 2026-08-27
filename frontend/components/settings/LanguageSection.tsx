"use client";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useLocale } from "@/lib/i18n";

/**
 * Interface-language picker, moved here from the workspace Topbar.
 *
 * Switching the language flips the whole product surface: the UI
 * strings, Henry's replies and every AI-generated text (lead
 * summaries, advice, email fallbacks) follow `users.language_code`,
 * hence the warning callout below the switcher.
 */
export function LanguageSection() {
  const { t } = useLocale();
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.language")}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 14,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="eyebrow" style={{ marginBottom: 4 }}>
            {t("settings.language.label")}
          </div>
          <div style={{ fontSize: 13.5, color: "var(--text-muted)" }}>
            {t("settings.language.help")}
          </div>
        </div>
        <LanguageSwitcher />
      </div>

      <div
        style={{
          padding: 12,
          borderRadius: 10,
          background: "color-mix(in srgb, var(--warm) 8%, transparent)",
          border:
            "1px solid color-mix(in srgb, var(--warm) 25%, var(--border))",
          fontSize: 13,
          lineHeight: 1.5,
          display: "flex",
          alignItems: "flex-start",
          gap: 10,
          color: "var(--text-muted)",
        }}
      >
        <span
          aria-hidden
          style={{
            color: "var(--warm)",
            fontWeight: 700,
            flexShrink: 0,
            lineHeight: 1.4,
          }}
        >
          !
        </span>
        <div>{t("settings.language.warning")}</div>
      </div>
    </div>
  );
}

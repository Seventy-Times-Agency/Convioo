/**
 * Context-free locale read for places that render OUTSIDE <LocaleProvider>
 * (error boundaries) or outside React entirely (toast helpers). Mirrors the
 * detection in lib/i18n.tsx: localStorage "convioo.lang" wins, then the legacy
 * key, then navigator.language, then Russian as the QA-team default.
 *
 * This intentionally does NOT depend on the i18n context so it can never throw
 * inside an error boundary.
 */
export type UiLang = "ru" | "uk" | "en";

const STORAGE_KEY = "convioo.lang";
const LEGACY_STORAGE_KEY = "leadgen.lang";

export function readUiLang(): UiLang {
  try {
    const stored =
      localStorage.getItem(STORAGE_KEY) || localStorage.getItem(LEGACY_STORAGE_KEY);
    if (stored === "ru" || stored === "uk" || stored === "en") return stored;
    const nav = (navigator.language || "").toLowerCase();
    if (nav.startsWith("uk")) return "uk";
    if (nav.startsWith("en")) return "en";
  } catch {
    // SSR / disabled storage — fall through
  }
  return "ru";
}

/** Pick the active-locale string from a tiny inline trilingual record. */
export function pickUiLang<T>(lang: UiLang, choices: Record<UiLang, T>): T {
  return choices[lang] ?? choices.ru;
}

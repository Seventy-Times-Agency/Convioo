"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ru } from "./i18n/ru";
import { en } from "./i18n/en";
import { uk } from "./i18n/uk";

/**
 * Minimal i18n for the open-demo web app.
 *
 * One flat dictionary per locale, looked up by dotted keys. No
 * interpolation, no pluralization — when a string needs a runtime
 * value the caller should pass the translated template to a helper
 * that does the substitution.
 *
 * Persists the selection in localStorage under "convioo.lang"; defaults
 * to Russian because the team that QAs the site is Russian-speaking.
 */

export type Locale = "ru" | "uk" | "en";

const STORAGE_KEY = "convioo.lang";
const LEGACY_STORAGE_KEY = "leadgen.lang";

const TRANSLATIONS = { ru, en, uk } as const;

export type TranslationKey = keyof (typeof TRANSLATIONS)["ru"];

type Ctx = {
  lang: Locale;
  setLang: (l: Locale) => void;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
};

const LocaleContext = createContext<Ctx | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Locale>("ru");

  useEffect(() => {
    let stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      stored = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (stored) {
        localStorage.setItem(STORAGE_KEY, stored);
        localStorage.removeItem(LEGACY_STORAGE_KEY);
      }
    }
    if (stored === "en" || stored === "ru" || stored === "uk") {
      setLangState(stored);
      return;
    }
    // First visit: auto-detect from navigator.language. Default stays
    // ru for users on locales we don't ship (so the QA team keeps
    // seeing Russian without re-clicking).
    try {
      const nav = (navigator.language || "").toLowerCase();
      if (nav.startsWith("uk")) setLangState("uk");
      else if (nav.startsWith("en")) setLangState("en");
    } catch {
      // SSR or restricted env — leave default
    }
  }, []);

  const setLang = useCallback((l: Locale) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // ignore quota / disabled storage
    }
    // Best-effort sync to the server so Henry's prompts pick the
    // matching language directive on the next turn. Failures are
    // intentional no-ops — UI is the source of truth, the column is
    // a convenience hint only.
    try {
      void fetch("/api/v1/users/me", {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language_code: l }),
      });
    } catch {
      // ignore — user may be logged-out on a public page
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => {
      const dict = TRANSLATIONS[lang] as Record<string, string>;
      // Fallback chain: uk falls through to ru (closer cognate) before en;
      // en/ru fall through to en. Mirrors the existing legacy behaviour
      // for the original two locales.
      const ruDict = TRANSLATIONS.ru as Record<string, string>;
      const raw =
        dict[key] ??
        (lang === "uk" ? ruDict[key] : undefined) ??
        TRANSLATIONS.en[key] ??
        key;
      if (!vars) return raw;
      return raw.replace(/\{(\w+)\}/g, (_, k) =>
        k in vars ? String(vars[k]) : `{${k}}`,
      );
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): Ctx {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error("useLocale must be used inside <LocaleProvider>");
  }
  return ctx;
}

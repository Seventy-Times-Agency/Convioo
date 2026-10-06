"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLocale, type TranslationKey } from "@/lib/i18n";

/** Вкладки внутри раздела рейла: «Добыча» = поиск + история запусков,
 * «Воронки» = воронки + шаблоны писем. Раньше вторые жили в меню под
 * аватаром. */
const SECTIONS: Record<string, { href: string; label: TranslationKey }[]> = {
  dobycha: [
    { href: "/app/search", label: "sec.newSearch" },
    { href: "/app/sessions", label: "sec.history" },
  ],
  funnels: [
    { href: "/app/funnels", label: "nav.funnels" },
    { href: "/app/templates", label: "sec.templates" },
  ],
};

export function SectionTabs({ section }: { section: keyof typeof SECTIONS }) {
  const pathname = usePathname() ?? "";
  const { t } = useLocale();
  return (
    <div style={{ display: "flex", gap: 2, borderBottom: "1px solid var(--border)", marginBottom: 14 }}>
      {SECTIONS[section].map((tab) => {
        const active = pathname === tab.href || pathname.startsWith(tab.href + "/");
        return (
          <Link
            key={tab.href}
            href={tab.href}
            style={{
              padding: "8px 14px",
              fontSize: 13.5,
              fontWeight: active ? 800 : 600,
              color: active ? "var(--text)" : "var(--text-muted)",
              borderBottom: active ? "2.5px solid var(--accent)" : "2.5px solid transparent",
              marginBottom: -1,
              textDecoration: "none",
              whiteSpace: "nowrap",
            }}
          >
            {t(tab.label)}
          </Link>
        );
      })}
    </div>
  );
}

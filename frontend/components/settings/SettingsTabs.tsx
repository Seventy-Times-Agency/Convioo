"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLocale, type TranslationKey } from "@/lib/i18n";

interface Tab {
  href: string;
  label: TranslationKey;
  /** Минимальная роль, ниже которой вкладка не рендерится. */
  min?: "admin" | "owner";
}

/** Вкладки один-в-один из макета Settings.dc.html; Журнал — только
 * админ и владелец, Биллинг — только владелец. */
const TABS: Tab[] = [
  { href: "/app/settings", label: "st.tab.company" },
  { href: "/app/settings/integrations", label: "st.tab.integrations" },
  { href: "/app/settings/telephony", label: "st.tab.telephony" },
  { href: "/app/settings/mail", label: "st.tab.mail" },
  { href: "/app/settings/journal", label: "st.tab.journal", min: "admin" },
  { href: "/app/settings/languages", label: "st.tab.languages" },
  { href: "/app/settings/billing", label: "st.tab.billing", min: "owner" },
];

export function SettingsTabs({ role }: { role: string | null }) {
  const pathname = usePathname();
  const { t } = useLocale();

  const visible = TABS.filter((tab) => {
    if (tab.min === "owner") return role === "owner";
    if (tab.min === "admin") return role === "owner" || role === "admin";
    return true;
  });

  return (
    <div
      style={{
        display: "flex",
        gap: 2,
        borderBottom: "1px solid var(--border)",
        overflowX: "auto",
        marginBottom: 18,
      }}
    >
      {visible.map((tab) => {
        const active =
          tab.href === "/app/settings"
            ? pathname === "/app/settings"
            : pathname?.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            style={{
              padding: "8px 15px",
              fontSize: 14,
              fontWeight: active ? 800 : 600,
              color: active ? "var(--text)" : "var(--text-muted)",
              borderBottom: active
                ? "2.5px solid var(--accent)"
                : "2.5px solid transparent",
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

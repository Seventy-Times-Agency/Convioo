"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLocale, type TranslationKey } from "@/lib/i18n";

interface Tab {
  href: string;
  label: TranslationKey;
  /** Кому видна вкладка. */
  roles: ("owner" | "admin")[];
}

/** Вкладки настроек команды. Личное (язык, безопасность, почта,
 * Telegram, уведомления) — в профиле, у всех ролей одинаково. */
const TABS: Tab[] = [
  { href: "/app/settings", label: "st.tab.company", roles: ["owner", "admin"] },
  { href: "/app/settings/comms", label: "st.tab.comms", roles: ["owner", "admin"] },
  { href: "/app/settings/connections", label: "st.tab.connections", roles: ["owner", "admin"] },
  { href: "/app/settings/billing", label: "st.tab.money", roles: ["owner"] },
  { href: "/app/settings/journal", label: "st.tab.journal", roles: ["owner", "admin"] },
];
const TECH: Tab = { href: "/app/settings/tech", label: "st.tab.tech", roles: ["owner"] };

export function SettingsTabs({ role }: { role: string | null }) {
  const pathname = usePathname();
  const { t } = useLocale();
  const can = (tab: Tab) => !!role && (tab.roles as string[]).includes(role);
  const isActive = (href: string) =>
    href === "/app/settings" ? pathname === "/app/settings" : !!pathname?.startsWith(href);

  const link = (tab: Tab, extra?: React.ReactNode) => {
    const active = isActive(tab.href);
    return (
      <Link
        key={tab.href}
        href={tab.href}
        className="tab-link"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "8px 15px",
          fontSize: 14,
          fontWeight: active ? 800 : 600,
          color: active ? "var(--text)" : "var(--text-muted)",
          borderBottom: active ? "2.5px solid var(--accent)" : "2.5px solid transparent",
          textDecoration: "none",
          whiteSpace: "nowrap",
        }}
      >
        {extra}
        {t(tab.label)}
      </Link>
    );
  };

  return (
    <div
      className="tabs-scroll"
      style={{
        display: "flex",
        gap: 2,
        borderBottom: "1px solid var(--border)",
        marginBottom: 18,
      }}
    >
      {TABS.filter(can).map((tab) => link(tab))}
      {can(TECH) && (
        <span style={{ marginLeft: "auto" }}>
          {link(TECH, <span className="st-dot wrn" style={{ marginRight: 0 }} />)}
        </span>
      )}
    </div>
  );
}

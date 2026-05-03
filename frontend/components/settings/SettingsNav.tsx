"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface Tab {
  href: string;
  label: string;
}

const TABS: Tab[] = [
  { href: "/app/settings", label: "Общие" },
  { href: "/app/settings/security", label: "Безопасность" },
  { href: "/app/settings/integrations", label: "Интеграции" },
  { href: "/app/settings/notifications", label: "Уведомления" },
  { href: "/app/settings/team", label: "Команда" },
];

export function SettingsNav() {
  const pathname = usePathname();

  return (
    <div
      style={{
        display: "flex",
        gap: 4,
        borderBottom: "1px solid var(--border)",
        marginBottom: 18,
        overflowX: "auto",
      }}
    >
      {TABS.map((tab) => {
        const active =
          tab.href === "/app/settings"
            ? pathname === "/app/settings"
            : pathname?.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            style={{
              padding: "10px 14px",
              fontSize: 13.5,
              fontWeight: active ? 600 : 500,
              color: active ? "var(--text)" : "var(--text-muted)",
              borderBottom: active
                ? "2px solid var(--accent)"
                : "2px solid transparent",
              marginBottom: -1,
              textDecoration: "none",
              whiteSpace: "nowrap",
            }}
          >
            {tab.label}
          </Link>
        );
      })}
    </div>
  );
}

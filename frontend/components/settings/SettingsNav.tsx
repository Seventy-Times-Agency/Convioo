"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLocale, type TranslationKey } from "@/lib/i18n";

interface Tab {
  href: string;
  label: TranslationKey;
}

const TABS: Tab[] = [
  { href: "/app/settings", label: "settings.tab.general" },
  { href: "/app/settings/security", label: "settings.tab.security" },
  { href: "/app/settings/integrations", label: "settings.tab.integrations" },
  { href: "/app/settings/webhooks", label: "settings.tab.webhooks" },
  { href: "/app/settings/notifications", label: "settings.tab.notifications" },
  { href: "/app/settings/team", label: "settings.tab.team" },
  { href: "/app/settings/billing", label: "settings.tab.billing" },
];

export function SettingsNav() {
  const pathname = usePathname();
  const { t } = useLocale();

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 4,
        borderBottom: "1px solid var(--border)",
        marginBottom: 18,
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
            {t(tab.label)}
          </Link>
        );
      })}
    </div>
  );
}

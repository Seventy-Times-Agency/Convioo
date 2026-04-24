"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "@/components/Icon";
import { useLocale, type TranslationKey } from "@/lib/i18n";

interface NavEntry {
  key: string;
  labelKey: TranslationKey;
  icon: IconName;
}

interface NavSection {
  sectionKey: TranslationKey;
}

type NavItem = NavEntry | NavSection;

const NAV: NavItem[] = [
  { sectionKey: "nav.workspace" },
  { key: "/app", labelKey: "nav.dashboard", icon: "home" },
  { key: "/app/search", labelKey: "nav.newSearch", icon: "sparkles" },
  { key: "/app/sessions", labelKey: "nav.sessions", icon: "folder" },
  { key: "/app/leads", labelKey: "nav.leads", icon: "list" },
  { sectionKey: "nav.team" },
  { key: "/app/team", labelKey: "nav.teamPage", icon: "users" },
  { key: "/app/profile", labelKey: "nav.profile", icon: "user" },
  { key: "/app/settings", labelKey: "nav.settings", icon: "settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { t } = useLocale();

  const isActive = (key: string) => {
    if (key === "/app") return pathname === "/app";
    return pathname === key || pathname.startsWith(key + "/");
  };

  return (
    <aside className="sidebar">
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 12px 20px" }}>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            background: "linear-gradient(135deg, var(--accent), #6a7bff)",
            display: "grid",
            placeItems: "center",
            color: "white",
            fontSize: 13,
            fontWeight: 700,
          }}
        >
          L
        </div>
        <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em" }}>Leadgen</div>
        <div className="chip" style={{ marginLeft: "auto", fontSize: 10, padding: "2px 7px" }}>
          beta
        </div>
      </div>

      {NAV.map((item, i) =>
        "sectionKey" in item ? (
          <div key={`sec-${i}`} className="nav-section">
            {t(item.sectionKey)}
          </div>
        ) : (
          <Link
            key={item.key}
            href={item.key}
            className={"nav-item" + (isActive(item.key) ? " active" : "")}
          >
            <Icon name={item.icon} size={17} />
            <span>{t(item.labelKey)}</span>
          </Link>
        ),
      )}
    </aside>
  );
}

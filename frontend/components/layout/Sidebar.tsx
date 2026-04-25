"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Icon, type IconName } from "@/components/Icon";
import {
  clearCurrentUser,
  getCurrentUser,
  userFullName,
  userInitials,
  type CurrentUser,
} from "@/lib/auth";
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
  const router = useRouter();
  const { t } = useLocale();
  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    setUser(getCurrentUser());
  }, []);

  const isActive = (key: string) => {
    if (key === "/app") return pathname === "/app";
    return pathname === key || pathname.startsWith(key + "/");
  };

  const handleLogout = () => {
    clearCurrentUser();
    router.push("/login");
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

      {user && (
        <div
          style={{
            marginTop: "auto",
            paddingTop: 16,
            borderTop: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div
            className="avatar"
            style={{
              background: "linear-gradient(135deg, var(--accent), #6a7bff)",
              color: "white",
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            {userInitials(user)}
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {userFullName(user)}
            </div>
          </div>
          <button
            type="button"
            className="btn-icon"
            onClick={handleLogout}
            title={t("nav.signOut")}
            aria-label={t("nav.signOut")}
          >
            <Icon name="logout" size={15} />
          </button>
        </div>
      )}
    </aside>
  );
}

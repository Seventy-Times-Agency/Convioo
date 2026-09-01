"use client";

import { useEffect, useRef, useState } from "react";
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
import { listMyTeams, type TeamSummary } from "@/lib/api";
import {
  clearActiveWorkspace,
  getActiveWorkspace,
  hasStoredWorkspace,
  setActiveWorkspace,
  setViewAsMember,
  subscribeWorkspace,
  PERSONAL_WORKSPACE,
  type Workspace,
} from "@/lib/workspace";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { useTheme } from "@/components/ThemeProvider";
import { closeMobileNav, useMobileNav } from "@/lib/mobileNav";

interface NavEntry {
  key: string;
  labelKey: TranslationKey;
  icon: IconName;
}

const PRIMARY_NAV: NavEntry[] = [
  { key: "/app", labelKey: "nav.home", icon: "home" },
  { key: "/app/search", labelKey: "nav.dobycha", icon: "search" },
  { key: "/app/leads", labelKey: "nav.base", icon: "users" },
  { key: "/app/inbox", labelKey: "nav.inbox", icon: "mail" },
];

const SECONDARY_NAV: NavEntry[] = [
  { key: "/app/templates", labelKey: "nav.templates", icon: "mail" },
  { key: "/app/sessions", labelKey: "nav.sessions", icon: "clock" },
  { key: "/app/sequences", labelKey: "nav.sequences", icon: "zap" },
  { key: "/app/connectors", labelKey: "nav.connectors", icon: "grid" },
  { key: "/app/affiliate", labelKey: "nav.affiliate", icon: "send" },
  { key: "/app/team", labelKey: "nav.teamPage", icon: "users" },
  { key: "/app/profile", labelKey: "nav.profile", icon: "user" },
  { key: "/app/settings", labelKey: "nav.settings", icon: "settings" },
  { key: "/developers", labelKey: "nav.developers", icon: "globe" },
];

/** Canonical role for nav filtering — mirrors the server's
 * normalize_role (legacy member→manager, viewer→sales). */
function normalizeRole(role: string | undefined | null): string {
  const r = (role ?? "").toLowerCase();
  if (r === "owner" || r === "admin" || r === "manager" || r === "sales")
    return r;
  if (r === "member") return "manager";
  return "sales";
}

/**
 * Role-aware nav, one-to-one with the approved mockups.
 *
 * The rail renders exactly what each role's mockup shows:
 *   sales   — Главная, Работа, Входящие                          (Main.dc.html)
 *   manager — + База, Добыча, Воронки, Аналитика, Команда        (MgrHome.dc.html)
 *   owner   — + Настройки                                        (OwnerHome.dc.html)
 *
 * Anything the mockups leave out (Шаблоны, Сессии, Последовательности,
 * Коннекторы, Подписка, Профиль) is still reachable — it moves into the
 * avatar menu at the foot of the rail rather than disappearing.
 *
 * Personal mode (no team) keeps the full product nav.
 */
function navForRole(role: string | null): {
  primary: NavEntry[];
  secondary: NavEntry[];
} {
  if (role === null) {
    return { primary: PRIMARY_NAV, secondary: SECONDARY_NAV };
  }

  const home: NavEntry = { key: "/app", labelKey: "nav.home", icon: "home" };
  const sales: NavEntry[] = [
    home,
    { key: "/app/work", labelKey: "nav.work", icon: "zap" },
    { key: "/app/inbox", labelKey: "nav.inbox", icon: "mail" },
  ];

  if (role === "sales") {
    return {
      primary: sales,
      secondary: [
        { key: "/app/templates", labelKey: "nav.templates", icon: "mail" },
        { key: "/app/profile", labelKey: "nav.profile", icon: "user" },
      ],
    };
  }

  // manager and up
  const primary: NavEntry[] = [
    ...sales,
    { key: "/app/leads", labelKey: "nav.base", icon: "users" },
    { key: "/app/search", labelKey: "nav.dobycha", icon: "search" },
    { key: "/app/funnels", labelKey: "nav.funnels", icon: "zap" },
    { key: "/app/team/analytics", labelKey: "nav.analytics", icon: "grid" },
    { key: "/app/team", labelKey: "nav.teamPage", icon: "users" },
  ];
  const secondary: NavEntry[] = [
    { key: "/app/templates", labelKey: "nav.templates", icon: "mail" },
    { key: "/app/sessions", labelKey: "nav.sessions", icon: "clock" },
    { key: "/app/sequences", labelKey: "nav.sequences", icon: "zap" },
    { key: "/app/profile", labelKey: "nav.profile", icon: "user" },
  ];

  if (role === "admin" || role === "owner") {
    primary.push({
      key: "/app/settings",
      labelKey: "nav.settings",
      icon: "settings",
    });
    secondary.push({
      key: "/app/connectors",
      labelKey: "nav.connectors",
      icon: "grid",
    });
  }
  if (role === "owner") {
    secondary.push({
      key: "/app/settings/billing",
      labelKey: "nav.billing",
      icon: "settings",
    });
  }
  return { primary, secondary };
}

/** data-tour hook the OnboardingTour looks for on each rail item. */
function tourId(key: string): string {
  return key.replace(/^\/app\/?/, "tour-") || "tour-dashboard";
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useLocale();
  const { resolved: theme, toggle: toggleTheme } = useTheme();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  const [workspace, setWorkspace] = useState<Workspace>(PERSONAL_WORKSPACE);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setUser(getCurrentUser());
    setWorkspace(getActiveWorkspace());
    listMyTeams()
      .then((rows) => {
        setTeams(rows);
        // Первый вход без сохранённого выбора: если пользователь
        // состоит в команде — сразу командное пространство (наш
        // инстанс командный; «Personal» остаётся явным выбором).
        if (!hasStoredWorkspace() && rows.length > 0) {
          setActiveWorkspace({
            kind: "team",
            team_id: rows[0].id,
            team_name: rows[0].name,
          });
        }
      })
      .catch(() => {
        // sidebar still renders fine without teams; ignore
      });
    return subscribeWorkspace(() => setWorkspace(getActiveWorkspace()));
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const isActive = (key: string) => {
    if (key === "/app") return pathname === "/app";
    return pathname === key || pathname.startsWith(key + "/");
  };

  const handleLogout = () => {
    clearCurrentUser();
    clearActiveWorkspace();
    router.push("/login");
  };

  // Role in the ACTIVE team drives which rail items render.
  const activeRole =
    workspace.kind === "team"
      ? normalizeRole(teams.find((tm) => tm.id === workspace.team_id)?.role)
      : null;
  const nav = navForRole(activeRole);

  const workspaceLabel =
    workspace.kind === "team" ? workspace.team_name : t("workspace.personal");
  const viewAsLabel =
    workspace.kind === "team" && workspace.view_as_user_id !== undefined
      ? workspace.view_as_name ?? `#${workspace.view_as_user_id}`
      : null;

  const isAdminAccount = (user as CurrentUser & { is_admin?: boolean })
    ?.is_admin;

  const mobileOpen = useMobileNav();

  return (
    <aside className={`sidebar rail${mobileOpen ? " open" : ""}`}>
      <Link
        href="/app"
        className="rail-mark"
        aria-label="Convloo"
        onClick={closeMobileNav}
      />

      <nav className="rail-nav" aria-label={t("nav.workspace")}>
        {nav.primary.map((item) => (
          <Link
            key={item.key}
            href={item.key}
            data-tour={tourId(item.key)}
            className={"rail-item" + (isActive(item.key) ? " active" : "")}
            onClick={closeMobileNav}
          >
            <Icon name={item.icon} size={17} />
            <span>{t(item.labelKey)}</span>
          </Link>
        ))}
      </nav>

      <div className="rail-foot" ref={menuRef}>
        <Link
          href="/app/help"
          className="rail-ghost"
          title={t("nav.help")}
          aria-label={t("nav.help")}
          onClick={closeMobileNav}
        >
          <Icon name="chat" size={18} />
        </Link>

        <button
          type="button"
          className="rail-ghost"
          onClick={toggleTheme}
          title={t(theme === "dark" ? "nav.themeLight" : "nav.themeDark")}
          aria-label={t(theme === "dark" ? "nav.themeLight" : "nav.themeDark")}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} size={17} />
        </button>

        {user && (
          <>
            <button
              type="button"
              className={"rail-avatar" + (menuOpen ? " open" : "")}
              onClick={() => setMenuOpen((v) => !v)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              title={userFullName(user)}
            >
              {userInitials(user)}
            </button>

            {menuOpen && (
              <div className="rail-menu" role="menu">
                <div className="rail-menu-head">
                  <div className="rail-menu-name">{userFullName(user)}</div>
                  <div className="rail-menu-sub">{workspaceLabel}</div>
                  {viewAsLabel && (
                    <div className="rail-menu-viewas">
                      {t("workspace.viewingAs", { name: viewAsLabel })}
                    </div>
                  )}
                </div>

                <div className="rail-menu-group">
                  <div className="rail-menu-label">{t("nav.workspace")}</div>
                  <WorkspaceOption
                    label={t("workspace.personal")}
                    active={workspace.kind === "personal"}
                    onClick={() => {
                      setActiveWorkspace(PERSONAL_WORKSPACE);
                      setMenuOpen(false);
                    }}
                  />
                  {teams.map((team) => (
                    <WorkspaceOption
                      key={team.id}
                      label={team.name}
                      hint={team.role}
                      active={
                        workspace.kind === "team" &&
                        workspace.team_id === team.id
                      }
                      onClick={() => {
                        setActiveWorkspace({
                          kind: "team",
                          team_id: team.id,
                          team_name: team.name,
                          view_as_user_id: undefined,
                          view_as_name: undefined,
                        });
                        setMenuOpen(false);
                      }}
                    />
                  ))}
                  {viewAsLabel && (
                    <button
                      type="button"
                      className="nav-item"
                      style={{ width: "100%" }}
                      onClick={() => {
                        setViewAsMember(undefined);
                        setMenuOpen(false);
                      }}
                    >
                      <Icon name="x" size={14} />
                      <span>{t("workspace.stopViewAs")}</span>
                    </button>
                  )}
                </div>

                {nav.secondary.length > 0 && (
                  <div className="rail-menu-group">
                    {nav.secondary.map((item) => (
                      <Link
                        key={item.key}
                        href={item.key}
                        role="menuitem"
                        className="nav-item"
                        style={{ width: "100%" }}
                        onClick={() => {
                          setMenuOpen(false);
                          closeMobileNav();
                        }}
                      >
                        <Icon name={item.icon} size={15} />
                        <span>{t(item.labelKey)}</span>
                      </Link>
                    ))}
                    {isAdminAccount && (
                      <Link
                        href="/app/admin"
                        role="menuitem"
                        className="nav-item"
                        style={{ width: "100%" }}
                        onClick={() => {
                          setMenuOpen(false);
                          closeMobileNav();
                        }}
                      >
                        <Icon name="star" size={15} />
                        <span>{t("nav.admin")}</span>
                      </Link>
                    )}
                  </div>
                )}

                <div className="rail-menu-group">
                  <button
                    type="button"
                    role="menuitem"
                    className="nav-item"
                    style={{ width: "100%" }}
                    onClick={() => {
                      setMenuOpen(false);
                      handleLogout();
                    }}
                  >
                    <Icon name="logout" size={15} />
                    <span>{t("nav.signOut")}</span>
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}

function WorkspaceOption({
  label,
  hint,
  active,
  onClick,
}: {
  label: string;
  hint?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        padding: "8px 10px",
        borderRadius: 8,
        border: "none",
        background: active ? "var(--accent-soft)" : "transparent",
        color: active ? "var(--accent)" : "var(--text)",
        cursor: "pointer",
        fontSize: 13,
        fontWeight: 500,
        textAlign: "left",
      }}
    >
      <span
        style={{
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </span>
      {hint && (
        <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{hint}</span>
      )}
      {active && !hint && <Icon name="check" size={13} />}
    </button>
  );
}

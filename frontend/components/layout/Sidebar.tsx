"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Icon, type IconName } from "@/components/brand/Icon";
import { NotificationBell } from "@/components/layout/NotificationBell";
import {
  getCurrentUser,
  setCurrentUserAvatar,
  subscribeCurrentUser,
  userFullName,
  userInitials,
  type CurrentUser,
} from "@/lib/auth";
import { normalizeRole, roleLabel } from "@/lib/roles";
import { getMyProfile, listMyTeams, type TeamSummary } from "@/lib/api";
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
import { useTheme } from "@/components/shell/ThemeProvider";
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
  { key: "/app/funnels", labelKey: "nav.funnels", icon: "zap" },
];

/** Страницы, которые живут вкладкой внутри раздела рейла: пока
 * открыта вкладка, подсвечен её раздел. */
const SECTION_ALIASES: Record<string, string[]> = {
  "/app/search": ["/app/sessions"],
  "/app/funnels": ["/app/templates", "/app/sequences"],
};

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
function navForRole(role: string | null | "loading"): {
  primary: NavEntry[];
  secondary: NavEntry[];
} {
  if (role === null) {
    return { primary: PRIMARY_NAV, secondary: [] };
  }
  // Список команд ещё едет: не рисуем меню селза владельцу на
  // полсекунды, только главную.
  if (role === "loading") {
    return {
      primary: [{ key: "/app", labelKey: "nav.home", icon: "home" }],
      secondary: [],
    };
  }

  const home: NavEntry = { key: "/app", labelKey: "nav.home", icon: "home" };
  const sales: NavEntry[] = [
    home,
    { key: "/app/work", labelKey: "nav.work", icon: "zap" },
  ];

  if (role === "sales") {
    return {
      // CRM открыта всем: селз видит в ней ровно свои лиды — это
      // серверное правило, интерфейс лишь не показывает раздачу.
      primary: [
        ...sales,
        { key: "/app/leads", labelKey: "nav.base", icon: "users" },
      ],
      secondary: [],
    };
  }

  // manager and up
  const primary: NavEntry[] = [
    ...sales,
    { key: "/app/base", labelKey: "nav.rawBase", icon: "folder" },
    { key: "/app/leads", labelKey: "nav.base", icon: "users" },
    { key: "/app/search", labelKey: "nav.dobycha", icon: "search" },
    { key: "/app/funnels", labelKey: "nav.funnels", icon: "zap" },
    { key: "/app/team/analytics", labelKey: "nav.analytics", icon: "grid" },
    { key: "/app/team", labelKey: "nav.teamPage", icon: "users" },
  ];
  const secondary: NavEntry[] = [];

  if (role === "admin" || role === "owner") {
    primary.push({
      key: "/app/settings",
      labelKey: "nav.settings",
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
  const [teamsLoaded, setTeamsLoaded] = useState(false);
  const [workspace, setWorkspace] = useState<Workspace>(PERSONAL_WORKSPACE);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Аватар меняют в профиле — кружок внизу рейла должен обновиться
  // без перезагрузки страницы.
  useEffect(() => subscribeCurrentUser(() => setUser(getCurrentUser())), []);

  useEffect(() => {
    setUser(getCurrentUser());
    setWorkspace(getActiveWorkspace());
    // Аватар живёт в профиле на сервере; кэш в localStorage только
    // чтобы не мигало — подтягиваем свежий при каждом входе в shell.
    getMyProfile()
      .then((p) => setCurrentUserAvatar(p.avatar_url ?? null))
      .catch(() => undefined);
    listMyTeams()
      .then((rows) => {
        setTeams(rows);
        setTeamsLoaded(true);
        // Первый вход без сохранённого выбора: если пользователь
        // состоит в команде — сразу командное пространство (наш
        // инстанс командный; «Personal» остаётся явным выбором).
        if (!hasStoredWorkspace() && rows.length > 0) {
          setActiveWorkspace({
            kind: "team",
            team_id: rows[0].id,
            team_name: rows[0].name,
          });
          return;
        }
        // Выбор мог протухнуть: команда осталась от прошлого аккаунта
        // — например, после демо-входа перед входом в свой. Держать
        // её нельзя: роль в ней не находится, normalizeRole роняет
        // владельца в "sales" и рисует урезанное меню, а запросы к
        // команде отвечают "not a team member".
        const stored = getActiveWorkspace();
        if (
          stored.kind === "team" &&
          !rows.some((row) => row.id === stored.team_id)
        ) {
          if (rows.length > 0) {
            setActiveWorkspace({
              kind: "team",
              team_id: rows[0].id,
              team_name: rows[0].name,
            });
          } else {
            clearActiveWorkspace();
          }
        }
      })
      .catch(() => {
        // Без списка команд меню строить не из чего — покажем
        // личный набор, а не меню селза.
        setTeamsLoaded(true);
      });
    return subscribeWorkspace(() => {
      const next = getActiveWorkspace();
      setWorkspace(next);
      // Команду только что создали или приняли инвайт: в teams её ещё
      // нет, и роль упала бы в sales. Перечитываем список.
      if (next.kind === "team") {
        setTeams((current) => {
          if (!current.some((tm) => tm.id === next.team_id)) {
            listMyTeams().then(setTeams).catch(() => undefined);
          }
          return current;
        });
      }
    });
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
    const under = (k: string) => pathname === k || pathname.startsWith(k + "/");
    // «Команда» не должна гореть вместе с «Аналитикой».
    if (key === "/app/team" && pathname.startsWith("/app/team/analytics")) return false;
    return under(key) || (SECTION_ALIASES[key] ?? []).some(under);
  };


  // Role in the ACTIVE team drives which rail items render.
  const activeTeam =
    workspace.kind === "team"
      ? teams.find((tm) => tm.id === workspace.team_id)
      : undefined;
  const activeRole: string | null | "loading" =
    workspace.kind !== "team"
      ? null
      : activeTeam
        ? normalizeRole(activeTeam.role)
        : teamsLoaded
          ? "sales"
          : "loading";
  const nav = navForRole(activeRole);

  const workspaceLabel =
    workspace.kind === "team" ? workspace.team_name : t("workspace.personal");
  const viewAsLabel =
    workspace.kind === "team" && workspace.view_as_user_id !== undefined
      ? workspace.view_as_name ?? `#${workspace.view_as_user_id}`
      : null;

  // Личное + команды; переключатель нужен, только если выбор есть.
  const workspaceCount = 1 + teams.length;
  const isAdminAccount = (user as CurrentUser & { is_admin?: boolean })
    ?.is_admin;

  const mobileOpen = useMobileNav();

  return (
    <aside className={`sidebar rail${mobileOpen ? " open" : ""}`}>
      <div className="rail-ws" ref={menuRef}>
        {workspaceCount > 1 ? (
          <button
            type="button"
            className={"rail-ws-badge" + (workspace.kind === "team" ? " team" : "") + (viewAsLabel ? " viewas" : "")}
            onClick={() => setMenuOpen((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            title={workspaceLabel}
          >
            {workspace.kind === "team" ? wsInitials(workspace.team_name) : ""}
            <span className="rail-ws-caret">▾</span>
          </button>
        ) : (
          <Link href="/app" className="rail-mark" aria-label="Convioo" onClick={closeMobileNav} />
        )}
        {menuOpen && (
          <div className="rail-menu rail-ws-menu" role="menu">
            <div className="rail-menu-label" style={{ padding: "6px 10px 4px" }}>{t("nav.workspace")}</div>
            {teams.map((team) => (
              <WorkspaceOption
                key={team.id}
                label={team.name}
                hint={roleLabel(t, team.role)}
                active={workspace.kind === "team" && workspace.team_id === team.id}
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
            <WorkspaceOption
              label={t("workspace.personal")}
              active={workspace.kind === "personal"}
              onClick={() => {
                setActiveWorkspace(PERSONAL_WORKSPACE);
                setMenuOpen(false);
              }}
            />
            {viewAsLabel && (
              <button
                type="button"
                className="nav-item"
                style={{ width: "100%", marginTop: 4 }}
                onClick={() => {
                  setViewAsMember(undefined);
                  setMenuOpen(false);
                }}
              >
                <Icon name="x" size={14} />
                <span>{t("workspace.stopViewAs")} · {viewAsLabel}</span>
              </button>
            )}
            {isAdminAccount && (
              <Link
                href="/app/admin"
                className="nav-item"
                style={{ width: "100%", marginTop: 4 }}
                onClick={() => {
                  setMenuOpen(false);
                  closeMobileNav();
                }}
              >
                <Icon name="star" size={14} />
                <span>{t("nav.admin")}</span>
              </Link>
            )}
          </div>
        )}
      </div>

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

      <div className="rail-foot">
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

        {user && <NotificationBell onNavigate={closeMobileNav} />}

        {user && (
          <Link
            href="/app/profile"
            className={"rail-avatar" + (isActive("/app/profile") ? " open" : "")}
            title={`${userFullName(user)} · ${t("nav.profile")}`}
            aria-label={t("nav.profile")}
            onClick={closeMobileNav}
            style={user.avatar_url ? { padding: 0, overflow: "hidden" } : undefined}
          >
            {user.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={user.avatar_url}
                alt=""
                style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "50%" }}
              />
            ) : (
              userInitials(user)
            )}
          </Link>
        )}
      </div>
    </aside>
  );
}

function wsInitials(name: string | undefined): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "C";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
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

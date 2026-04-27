"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Icon, type IconName } from "@/components/Icon";
import { ConviooWordmark } from "@/components/ConviooLogo";
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
  setActiveWorkspace,
  setViewAsMember,
  subscribeWorkspace,
  PERSONAL_WORKSPACE,
  type Workspace,
} from "@/lib/workspace";
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
  { key: "/app/templates", labelKey: "nav.templates", icon: "mail" },
  { sectionKey: "nav.team" },
  { key: "/app/team", labelKey: "nav.teamPage", icon: "users" },
  { key: "/app/profile", labelKey: "nav.profile", icon: "user" },
  { key: "/app/billing", labelKey: "nav.billing", icon: "zap" },
  { key: "/app/settings", labelKey: "nav.settings", icon: "settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useLocale();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  const [workspace, setWorkspace] = useState<Workspace>(PERSONAL_WORKSPACE);
  const [pickerOpen, setPickerOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setUser(getCurrentUser());
    setWorkspace(getActiveWorkspace());
    listMyTeams()
      .then(setTeams)
      .catch(() => {
        // sidebar still renders fine without teams; ignore
      });
    return subscribeWorkspace(() => setWorkspace(getActiveWorkspace()));
  }, []);

  useEffect(() => {
    if (!pickerOpen) return;
    const onClick = (e: MouseEvent) => {
      if (
        pickerRef.current &&
        !pickerRef.current.contains(e.target as Node)
      ) {
        setPickerOpen(false);
      }
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [pickerOpen]);

  const isActive = (key: string) => {
    if (key === "/app") return pathname === "/app";
    return pathname === key || pathname.startsWith(key + "/");
  };

  const handleLogout = () => {
    clearCurrentUser();
    clearActiveWorkspace();
    router.push("/login");
  };

  const workspaceLabel =
    workspace.kind === "team" ? workspace.team_name : t("workspace.personal");
  const viewAsLabel =
    workspace.kind === "team" && workspace.view_as_user_id !== undefined
      ? workspace.view_as_name ?? `#${workspace.view_as_user_id}`
      : null;

  return (
    <aside className="sidebar">
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 12px 14px" }}>
        <ConviooWordmark height={24} fallbackTextSize={14} />
        <div className="chip" style={{ marginLeft: "auto", fontSize: 10, padding: "2px 7px" }}>
          beta
        </div>
      </div>

      <div style={{ position: "relative", padding: "0 12px 16px" }} ref={pickerRef}>
        <button
          type="button"
          onClick={() => setPickerOpen((v) => !v)}
          style={{
            width: "100%",
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: "8px 10px",
            display: "flex",
            alignItems: "center",
            gap: 10,
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          <div
            style={{
              width: 24,
              height: 24,
              borderRadius: 6,
              background:
                workspace.kind === "team"
                  ? "linear-gradient(135deg, #EC4899, #F59E0B)"
                  : "var(--surface)",
              border: "1px solid var(--border)",
              display: "grid",
              placeItems: "center",
              fontSize: 11,
              fontWeight: 700,
              color: workspace.kind === "team" ? "white" : "var(--text-muted)",
              flexShrink: 0,
            }}
          >
            {workspace.kind === "team" ? workspace.team_name.charAt(0).toUpperCase() : "·"}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="eyebrow" style={{ fontSize: 9, marginBottom: 1 }}>
              {t("workspace.label")}
            </div>
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {workspaceLabel}
            </div>
            {viewAsLabel && (
              <div
                style={{
                  fontSize: 10.5,
                  color: "var(--accent)",
                  marginTop: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {t("workspace.viewingAs", { name: viewAsLabel })}
              </div>
            )}
          </div>
          <Icon name="chevronDown" size={14} style={{ color: "var(--text-dim)" }} />
        </button>

        {pickerOpen && (
          <div
            style={{
              position: "absolute",
              top: "100%",
              left: 12,
              right: 12,
              marginTop: 4,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              boxShadow: "var(--shadow-lg)",
              padding: 6,
              zIndex: 50,
            }}
          >
            <WorkspaceOption
              label={t("workspace.personal")}
              active={workspace.kind === "personal"}
              onClick={() => {
                setActiveWorkspace(PERSONAL_WORKSPACE);
                setPickerOpen(false);
              }}
            />
            {teams.map((team) => (
              <WorkspaceOption
                key={team.id}
                label={team.name}
                hint={team.role}
                active={
                  workspace.kind === "team" && workspace.team_id === team.id
                }
                onClick={() => {
                  setActiveWorkspace({
                    kind: "team",
                    team_id: team.id,
                    team_name: team.name,
                    view_as_user_id: undefined,
                    view_as_name: undefined,
                  });
                  setPickerOpen(false);
                }}
              />
            ))}
            {viewAsLabel && (
              <button
                type="button"
                className="nav-item"
                onClick={() => {
                  setViewAsMember(undefined);
                  setPickerOpen(false);
                }}
                style={{ width: "100%", marginTop: 4 }}
              >
                <Icon name="x" size={14} />
                <span>{t("workspace.stopViewAs")}</span>
              </button>
            )}
            <button
              type="button"
              className="nav-item"
              onClick={() => {
                setPickerOpen(false);
                router.push("/app/team");
              }}
              style={{
                width: "100%",
                marginTop: 4,
                paddingTop: 8,
                borderTop: "1px solid var(--border)",
              }}
            >
              <Icon name="plus" size={14} />
              <span>{t("workspace.manage")}</span>
            </button>
          </div>
        )}
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

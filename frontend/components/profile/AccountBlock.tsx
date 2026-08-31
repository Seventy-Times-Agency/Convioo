"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui";
import {
  clearCurrentUser,
  getCurrentUser,
  userFullName,
  userInitials,
  type CurrentUser,
} from "@/lib/auth";
import { listMyTeams, type TeamSummary } from "@/lib/api";
import { clearActiveWorkspace, getActiveWorkspace } from "@/lib/workspace";
import { useLocale, type Locale } from "@/lib/i18n";
import { useRouter } from "next/navigation";
import { roleLabel } from "@/lib/roles";

const LANGS: { code: Locale; label: string }[] = [
  { code: "uk", label: "Українська" },
  { code: "ru", label: "Русский" },
  { code: "en", label: "English" },
];

/**
 * Профиль аккаунта — Profile.dc.html: кто я, на каком языке вижу
 * интерфейс, чем защищён вход.
 *
 * Важное различие, которое макет проговаривает прямым текстом: язык
 * интерфейса — личный, а язык писем клиентам задаётся воронкой. Это
 * два разных языка, и их путают, поэтому подпись под переключателем
 * оставлена дословно.
 *
 * Переключателей уведомлений из макета здесь два из трёх нет:
 * «горячий ответ» и «напоминания о перезвонах» — события отдела уже
 * отправляются, но выключить их персонально пока нечем, для этого
 * нужны поля у пользователя.
 */
export function AccountBlock() {
  const { t, lang, setLang } = useLocale();
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [teams, setTeams] = useState<TeamSummary[]>([]);

  useEffect(() => {
    setUser(getCurrentUser());
    listMyTeams()
      .then(setTeams)
      .catch(() => undefined);
  }, []);

  if (!user) return null;

  const ws = getActiveWorkspace();
  const team =
    ws.kind === "team" ? teams.find((x) => x.id === ws.team_id) : undefined;

  const logout = () => {
    clearCurrentUser();
    clearActiveWorkspace();
    router.push("/login");
  };

  return (
    <div
      className="card"
      style={{ padding: 18, marginBottom: 14, display: "grid", gap: 18 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div
          className="avatar"
          style={{
            width: 46,
            height: 46,
            fontSize: 17,
            fontWeight: 800,
            background: "var(--gradient3)",
            color: "white",
            flexShrink: 0,
          }}
        >
          {userInitials(user)}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 19, fontWeight: 800 }}>
            {userFullName(user)}
          </div>
          <div
            style={{
              fontSize: 12.5,
              color: "var(--text-muted)",
              marginTop: 2,
            }}
          >
            {team
              ? t("profile.roleLine", {
                  role: roleLabel(t, team.role),
                  team: team.name,
                })
              : t("profile.noTeam")}
          </div>
        </div>
      </div>

      <div>
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          {t("profile.uiLanguage")}
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {LANGS.map((l) => (
            <Button
              key={l.code}
              variant={lang === l.code ? "primary" : "ghost"}
              size="sm"
              onClick={() => setLang(l.code)}
            >
              {l.label}
            </Button>
          ))}
        </div>
        <div
          style={{
            fontSize: 11.5,
            color: "var(--text-dim)",
            marginTop: 8,
            lineHeight: 1.5,
          }}
        >
          {t("profile.uiLanguageHint")}
        </div>
      </div>

      <div>
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          {t("profile.security")}
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link href="/app/settings/security" className="btn btn-ghost btn-sm">
            <Icon name="settings" size={14} />
            {t("profile.changePassword")}
          </Link>
          <Button variant="ghost" size="sm" onClick={logout}>
            <Icon name="logout" size={14} />
            {t("nav.signOut")}
          </Button>
        </div>
      </div>
    </div>
  );
}

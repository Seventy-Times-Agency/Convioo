"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/brand/Icon";
import { Avatar, Button } from "@/components/ui";
import {
  getCurrentUser,
  setCurrentUserAvatar,
  subscribeCurrentUser,
  userFullName,
  userInitials,
  type CurrentUser,
} from "@/lib/auth";
import { listMyTeams, updateMyProfile, type TeamSummary } from "@/lib/api";
import { fileToAvatarDataUrl } from "@/lib/avatar";
import { showError } from "@/lib/toast";
import { getActiveWorkspace, subscribeWorkspace } from "@/lib/workspace";
import { logout as endSession } from "@/lib/session";
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
  const [avatarBusy, setAvatarBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setUser(getCurrentUser());
    listMyTeams()
      .then(setTeams)
      .catch(() => undefined);
    return subscribeCurrentUser(() => setUser(getCurrentUser()));
  }, []);

  const pickAvatar = async (file: File | undefined) => {
    if (!file) return;
    setAvatarBusy(true);
    try {
      const dataUrl = await fileToAvatarDataUrl(file);
      const p = await updateMyProfile({ avatar_url: dataUrl });
      setCurrentUserAvatar(p.avatar_url ?? dataUrl);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setAvatarBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const removeAvatar = async () => {
    setAvatarBusy(true);
    try {
      await updateMyProfile({ avatar_url: null });
      setCurrentUserAvatar(null);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setAvatarBusy(false);
    }
  };

  if (!user) return null;

  const ws = getActiveWorkspace();
  const team =
    ws.kind === "team" ? teams.find((x) => x.id === ws.team_id) : undefined;

  const logout = () => {
    void endSession().finally(() => router.push("/login"));
  };

  return (
    <>
      {/* Карточка человека: фото, имя, роль — фото меняется кликом. */}
      <div className="card" style={{ padding: 20, textAlign: "center" }}>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={avatarBusy}
          title={t("profile.avatar.change")}
          style={{
            background: "none",
            border: "none",
            padding: 0,
            cursor: "pointer",
            position: "relative",
            opacity: avatarBusy ? 0.6 : 1,
          }}
        >
          <Avatar
            src={user.avatar_url}
            initials={userInitials(user)}
            size={76}
            style={{ background: "var(--gradient3)", color: "white", fontWeight: 800 }}
          />
          <span
            style={{
              position: "absolute",
              right: 0,
              bottom: 0,
              width: 24,
              height: 24,
              borderRadius: "50%",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              display: "grid",
              placeItems: "center",
              color: "var(--text-muted)",
            }}
          >
            <Icon name="pencil" size={11} />
          </span>
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => void pickAvatar(e.target.files?.[0])}
        />
        <div style={{ fontSize: 17, fontWeight: 800, marginTop: 10 }}>{userFullName(user)}</div>
        <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 2 }}>
          {team
            ? t("profile.roleLine", { role: roleLabel(t, team.role), team: team.name })
            : t("profile.noTeam")}
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 12, flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => fileRef.current?.click()}
            disabled={avatarBusy}
          >
            {user.avatar_url ? t("profile.avatar.change") : t("profile.avatar.upload")}
          </button>
          {user.avatar_url && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={removeAvatar} disabled={avatarBusy}>
              {t("profile.avatar.remove")}
            </button>
          )}
        </div>
      </div>

      <div className="card" style={{ padding: 18 }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>{t("profile.uiLanguage")}</div>
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
        <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 8, lineHeight: 1.5 }}>
          {t("profile.uiLanguageHint")}
        </div>
        <div style={{ borderTop: "1px solid var(--border)", marginTop: 14, paddingTop: 12 }}>
          <Button variant="ghost" size="sm" onClick={logout}>
            <Icon name="logout" size={14} />
            {t("nav.signOut")}
          </Button>
        </div>
      </div>
    </>
  );
}

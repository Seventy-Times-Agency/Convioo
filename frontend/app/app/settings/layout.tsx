"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { SettingsTabs } from "@/components/settings/SettingsTabs";
import { getTeamDetail } from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";

/**
 * Настройки — Settings.dc.html. Вкладки макета вместо старой левой
 * навигации; заголовок несёт имя команды, чтобы было видно, чьи
 * это настройки. Роль решает, какие вкладки рендерить.
 */
export default function SettingsLayout({ children }: { children: ReactNode }) {
  const { t } = useLocale();
  const [teamName, setTeamName] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => subscribeWorkspace(() => setTick((n) => n + 1)), []);

  useEffect(() => {
    const id = activeTeamId();
    if (!id) {
      setTeamName(null);
      setRole(null);
      return;
    }
    getTeamDetail(id)
      .then((d) => {
        setTeamName(d.name);
        setRole(d.role);
      })
      .catch(() => {
        setTeamName(null);
        setRole(null);
      });
  }, [tick]);

  return (
    <>
      <Topbar
        title={t("settings.title")}
        subtitle={
          teamName
            ? t("st.scopeTeam", { name: teamName })
            : t("st.scopePersonal")
        }
      />
      <div className="page" style={{ maxWidth: 1180 }}>
        <SettingsTabs role={role} />
        {children}
      </div>
    </>
  );
}

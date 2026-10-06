"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { SettingsTabs } from "@/components/settings/SettingsTabs";
import { getTeamDetail } from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { normalizeRole } from "@/lib/roles";

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
    let cancelled = false;
    getTeamDetail(id)
      .then((d) => {
        if (cancelled) return;
        setTeamName(d.name);
        setRole(normalizeRole(d.role));
      })
      .catch(() => {
        if (cancelled) return;
        setTeamName(null);
        setRole(null);
      });
    // Быстрое переключение команд: ответ прошлой не должен
    // перезаписать имя и вкладки текущей.
    return () => {
      cancelled = true;
    };
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
        {role && role !== "owner" && role !== "admin" ? (
          <div className="card" style={{ padding: 24, fontSize: 13.5, color: "var(--text-muted)", lineHeight: 1.6 }}>
            {t("st.personalOnly")}{" "}
            <Link href="/app/profile" style={{ color: "var(--accent)" }}>{t("nav.profile")} →</Link>
          </div>
        ) : (
          children
        )}
      </div>
    </>
  );
}

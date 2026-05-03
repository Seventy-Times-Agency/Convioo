"use client";

import type { ReactNode } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { SettingsNav } from "@/components/settings/SettingsNav";
import { useLocale } from "@/lib/i18n";

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const { t } = useLocale();
  return (
    <>
      <Topbar title={t("settings.title")} subtitle={t("settings.subtitle")} />
      <div className="page" style={{ maxWidth: 720 }}>
        <SettingsNav />
        {children}
      </div>
    </>
  );
}

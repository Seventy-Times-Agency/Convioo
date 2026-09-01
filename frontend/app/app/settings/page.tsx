"use client";

import { BrandingSection } from "@/components/settings/BrandingSection";
import { ICPSection } from "@/components/settings/ICPSection";

/** Компания — профиль команды: брендинг отчётов и портрет клиента.
 *  Личные разделы (аккаунт, безопасность, уведомления) живут в
 *  Кабинете. */
export default function SettingsCompanyPage() {
  return (
    <>
      <BrandingSection />
      <ICPSection />
    </>
  );
}

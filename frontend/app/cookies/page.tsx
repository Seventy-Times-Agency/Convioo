"use client";

import { LegalShell } from "@/components/LegalShell";
import { useLocale } from "@/lib/i18n";

export default function CookiesPage() {
  const { t } = useLocale();
  return (
    <LegalShell title={t("legal.cookies.title")} updated="2026-04-27">
      <p>{t("legal.cookies.intro")}</p>

      <h2>{t("legal.cookies.what.title")}</h2>
      <p>{t("legal.cookies.what.body")}</p>

      <h2>{t("legal.cookies.use.title")}</h2>
      <ul>
        <li>{t("legal.cookies.use.li1")}</li>
        <li>{t("legal.cookies.use.li2")}</li>
        <li>{t("legal.cookies.use.li3")}</li>
      </ul>

      <h2>{t("legal.cookies.thirdparty.title")}</h2>
      <p>{t("legal.cookies.thirdparty.body")}</p>

      <h2>{t("legal.cookies.control.title")}</h2>
      <p>{t("legal.cookies.control.body")}</p>
    </LegalShell>
  );
}

"use client";

import { LegalShell } from "@/components/LegalShell";
import { useLocale } from "@/lib/i18n";

export default function PrivacyPage() {
  const { t } = useLocale();
  return (
    <LegalShell title={t("legal.privacy.title")} updated="2026-04-27">
      <p>{t("legal.privacy.intro")}</p>

      <h2>{t("legal.privacy.collect.title")}</h2>
      <p>{t("legal.privacy.collect.body")}</p>
      <ul>
        <li>{t("legal.privacy.collect.li1")}</li>
        <li>{t("legal.privacy.collect.li2")}</li>
        <li>{t("legal.privacy.collect.li3")}</li>
      </ul>

      <h2>{t("legal.privacy.use.title")}</h2>
      <p>{t("legal.privacy.use.body")}</p>

      <h2>{t("legal.privacy.share.title")}</h2>
      <p>{t("legal.privacy.share.body")}</p>
      <ul>
        <li>{t("legal.privacy.share.li1")}</li>
        <li>{t("legal.privacy.share.li2")}</li>
        <li>{t("legal.privacy.share.li3")}</li>
      </ul>

      <h2>{t("legal.privacy.rights.title")}</h2>
      <p>{t("legal.privacy.rights.body")}</p>

      <h2>{t("legal.privacy.retention.title")}</h2>
      <p>{t("legal.privacy.retention.body")}</p>

      <h2>{t("legal.privacy.contact.title")}</h2>
      <p>{t("legal.privacy.contact.body")}</p>
    </LegalShell>
  );
}

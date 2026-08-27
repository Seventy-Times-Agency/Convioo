"use client";

import { LegalShell } from "@/components/LegalShell";
import { useLocale } from "@/lib/i18n";

export default function TermsPage() {
  const { t } = useLocale();
  return (
    <LegalShell title={t("legal.terms.title")} updated="2026-04-27">
      <p>{t("legal.terms.intro")}</p>

      <h2>{t("legal.terms.account.title")}</h2>
      <p>{t("legal.terms.account.body")}</p>

      <h2>{t("legal.terms.allowed.title")}</h2>
      <p>{t("legal.terms.allowed.body")}</p>
      <ul>
        <li>{t("legal.terms.allowed.li1")}</li>
        <li>{t("legal.terms.allowed.li2")}</li>
        <li>{t("legal.terms.allowed.li3")}</li>
      </ul>

      <h2>{t("legal.terms.payments.title")}</h2>
      <p>{t("legal.terms.payments.body")}</p>

      <h2>{t("legal.terms.warranty.title")}</h2>
      <p>{t("legal.terms.warranty.body")}</p>

      <h2>{t("legal.terms.termination.title")}</h2>
      <p>{t("legal.terms.termination.body")}</p>

      <h2>{t("legal.terms.law.title")}</h2>
      <p>{t("legal.terms.law.body")}</p>
    </LegalShell>
  );
}

"use client";

import { Topbar } from "@/components/layout/Topbar";
import { ConnectorsGallery } from "@/components/app/ConnectorsGallery";
import { useLocale } from "@/lib/i18n";

export default function ConnectorsPage() {
  const { t } = useLocale();
  return (
    <>
      <Topbar
        title={t("connectors.title")}
        subtitle={t("connectors.subtitle")}
      />
      <div className="page">
        <ConnectorsGallery />
      </div>
    </>
  );
}

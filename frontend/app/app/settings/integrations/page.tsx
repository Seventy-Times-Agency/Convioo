"use client";

import Link from "next/link";
import { ICPSection } from "@/components/settings/ICPSection";
import { BackendInfoCards } from "@/components/settings/BackendInfoCards";
import { Icon } from "@/components/Icon";
import { useLocale } from "@/lib/i18n";

/**
 * The per-provider connector forms moved to the dedicated Connectors
 * marketplace (/app/connectors). This Settings tab now keeps only the
 * ideal-customer-profile config (not a connector) plus a pointer to the
 * marketplace, so connectors are discoverable from the left nav instead
 * of buried at the bottom of a long Settings page.
 */
export default function SettingsIntegrationsPage() {
  const { t } = useLocale();
  return (
    <>
      <Link
        href="/app/connectors"
        className="card"
        style={{
          padding: 18,
          marginBottom: 14,
          display: "flex",
          alignItems: "center",
          gap: 14,
          textDecoration: "none",
          color: "inherit",
        }}
      >
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 10,
            background: "var(--accent-soft)",
            color: "var(--accent)",
            display: "grid",
            placeItems: "center",
            flexShrink: 0,
          }}
        >
          <Icon name="grid" size={20} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14.5, fontWeight: 600 }}>
            {t("connectors.title")}
          </div>
          <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
            {t("connectors.movedHint")}
          </div>
        </div>
        <Icon name="chevronRight" size={18} style={{ color: "var(--text-dim)" }} />
      </Link>

      <ICPSection />
      <BackendInfoCards />
    </>
  );
}

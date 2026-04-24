"use client";

import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { useLocale } from "@/lib/i18n";

export default function ProfilePage() {
  const { t } = useLocale();
  const empty = t("profile.empty");
  return (
    <>
      <Topbar title={t("profile.title")} subtitle={t("profile.subtitle")} />
      <div className="page" style={{ maxWidth: 720 }}>
        <div className="card" style={{ padding: 28, marginBottom: 16 }}>
          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}
          >
            <Field label={t("profile.field.business")} value={empty} />
            <Field label={t("profile.field.region")} value={empty} />
            <Field label={t("profile.field.offer")} value={empty} />
            <Field label={t("profile.field.niches")} value={empty} />
          </div>
        </div>
        <div
          className="card"
          style={{ padding: 20, background: "var(--surface-2)" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Icon name="sparkles" size={16} style={{ color: "var(--accent)" }} />
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              {t("profile.hint")}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, color: "var(--text-muted)" }}>{value}</div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { getMyProfile, type UserProfile } from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";

const AGE_LABEL_KEY: Record<string, TranslationKey> = {
  "<18": "onboarding.age.lt18",
  "18-24": "onboarding.age.18_24",
  "25-34": "onboarding.age.25_34",
  "35-44": "onboarding.age.35_44",
  "45-54": "onboarding.age.45_54",
  "55+": "onboarding.age.55plus",
};

const SIZE_LABEL_KEY: Record<string, TranslationKey> = {
  solo: "onboarding.size.solo",
  small: "onboarding.size.small",
  medium: "onboarding.size.medium",
  large: "onboarding.size.large",
};

export default function ProfilePage() {
  const { t } = useLocale();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMyProfile()
      .then(setProfile)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const empty = t("profile.empty");

  const ageLabel = profile?.age_range
    ? t(AGE_LABEL_KEY[profile.age_range] ?? ("profile.empty" as TranslationKey))
    : empty;
  const sizeLabel = profile?.business_size
    ? t(SIZE_LABEL_KEY[profile.business_size] ?? ("profile.empty" as TranslationKey))
    : empty;

  return (
    <>
      <Topbar
        title={t("profile.title")}
        subtitle={t("profile.subtitle")}
        right={
          <Link href="/onboarding" className="btn btn-ghost btn-sm">
            <Icon name="pencil" size={14} /> {t("common.edit")}
          </Link>
        }
      />
      <div className="page" style={{ maxWidth: 720 }}>
        {error && (
          <div
            className="card"
            style={{
              padding: 14,
              color: "var(--cold)",
              borderColor: "var(--cold)",
              marginBottom: 16,
            }}
          >
            {error}
          </div>
        )}
        <div className="card" style={{ padding: 28, marginBottom: 16 }}>
          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}
          >
            <Field label={t("profile.field.business")} value={sizeLabel} />
            <Field
              label={t("profile.field.region")}
              value={profile?.home_region || empty}
            />
            <Field
              label={t("profile.field.offer")}
              value={profile?.profession || empty}
            />
            <Field
              label={t("profile.field.niches")}
              value={
                profile?.niches && profile.niches.length > 0
                  ? profile.niches.join(", ")
                  : empty
              }
            />
            <Field label={t("profile.field.age")} value={ageLabel} />
            <Field
              label={t("profile.field.displayName")}
              value={profile?.display_name || empty}
            />
          </div>
          {profile?.service_description && (
            <div style={{ marginTop: 18 }}>
              <div className="eyebrow" style={{ marginBottom: 6 }}>
                {t("profile.field.offerRaw")}
              </div>
              <div
                style={{
                  fontSize: 14,
                  color: "var(--text-muted)",
                  lineHeight: 1.55,
                }}
              >
                {profile.service_description}
              </div>
            </div>
          )}
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

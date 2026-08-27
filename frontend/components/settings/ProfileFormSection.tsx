"use client";

import React, { useMemo } from "react";
import { Icon } from "@/components/Icon";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { suggestNiches, type UserProfile } from "@/lib/api";
import { showError } from "@/lib/toast";
import { useState } from "react";

// Mirror of UserProfileUpdate.service_description max_length on the
// backend — keep in sync. The textarea hard-stops at this count and a
// counter is shown so the user knows how much room is left.
export const SERVICE_DESCRIPTION_MAX = 800;

export const AGE_OPTIONS: { code: string; labelKey: TranslationKey }[] = [
  { code: "<18", labelKey: "onboarding.age.lt18" },
  { code: "18-24", labelKey: "onboarding.age.18_24" },
  { code: "25-34", labelKey: "onboarding.age.25_34" },
  { code: "35-44", labelKey: "onboarding.age.35_44" },
  { code: "45-54", labelKey: "onboarding.age.45_54" },
  { code: "55+", labelKey: "onboarding.age.55plus" },
];

export const SIZE_OPTIONS: { code: string; labelKey: TranslationKey }[] = [
  { code: "solo", labelKey: "onboarding.size.solo" },
  { code: "small", labelKey: "onboarding.size.small" },
  { code: "medium", labelKey: "onboarding.size.medium" },
  { code: "large", labelKey: "onboarding.size.large" },
];

export const GENDER_OPTIONS: { code: string; labelKey: TranslationKey }[] = [
  { code: "male", labelKey: "auth.field.gender.male" },
  { code: "female", labelKey: "auth.field.gender.female" },
  { code: "other", labelKey: "auth.field.gender.other" },
];

export const AGE_LABEL_KEY: Record<string, TranslationKey> = Object.fromEntries(
  AGE_OPTIONS.map((o) => [o.code, o.labelKey]),
);

export const SIZE_LABEL_KEY: Record<string, TranslationKey> = Object.fromEntries(
  SIZE_OPTIONS.map((o) => [o.code, o.labelKey]),
);

export const GENDER_LABEL_KEY: Record<string, TranslationKey> = Object.fromEntries(
  GENDER_OPTIONS.map((o) => [o.code, o.labelKey]),
);

export interface DraftState {
  display_name: string;
  age_range: string | null;
  gender: string | null;
  business_size: string | null;
  service_description: string;
  home_region: string;
  niches: string[];
  calendly_url: string;
}

export function profileToDraft(p: UserProfile): DraftState {
  return {
    display_name: p.display_name ?? "",
    age_range: p.age_range,
    gender: p.gender,
    business_size: p.business_size,
    service_description: p.service_description ?? "",
    home_region: p.home_region ?? "",
    niches: p.niches ?? [],
    calendly_url: p.calendly_url ?? "",
  };
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, color: "var(--text-muted)" }}>{value}</div>
    </div>
  );
}

function EditorField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div className="eyebrow">{label}</div>
      {children}
    </div>
  );
}

function ChipPicker({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {options.map((o) => {
        const active = value === o.value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(active ? null : o.value)}
            style={{
              padding: "7px 13px",
              fontSize: 13,
              borderRadius: 999,
              cursor: "pointer",
              border: active
                ? "1px solid var(--accent)"
                : "1px solid var(--border)",
              background: active
                ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                : "var(--surface)",
              color: active ? "var(--accent)" : "var(--text)",
              fontWeight: active ? 600 : 500,
            }}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function CharCounter({ value, max }: { value: string; max: number }) {
  const len = value.length;
  const remaining = max - len;
  // Subtle until you cross 90% of the cap, then warn — the user gets
  // a visible heads-up before the textarea hard-stops their next key.
  const warn = remaining < max * 0.1;
  return (
    <div
      style={{
        marginTop: 4,
        fontSize: 11.5,
        color: warn ? "var(--warm)" : "var(--text-dim)",
        textAlign: "right",
      }}
    >
      {len} / {max}
    </div>
  );
}

export function ProfileFormSection({
  profile,
  editing,
  draft,
  savedTick,
  onDraftChange,
}: {
  profile: UserProfile | null;
  editing: boolean;
  draft: DraftState | null;
  savedTick: number;
  onDraftChange: (d: DraftState) => void;
}) {
  const { t } = useLocale();
  const [nicheInput, setNicheInput] = useState("");
  const [nicheSuggestions, setNicheSuggestions] = useState<string[] | null>(null);
  const [suggestingNiches, setSuggestingNiches] = useState(false);

  const empty = t("profile.empty");

  const ageLabel = useMemo(() => {
    if (!profile?.age_range) return empty;
    const key = AGE_LABEL_KEY[profile.age_range];
    return key ? t(key) : profile.age_range;
  }, [profile?.age_range, empty, t]);

  const sizeLabel = useMemo(() => {
    if (!profile?.business_size) return empty;
    const key = SIZE_LABEL_KEY[profile.business_size];
    return key ? t(key) : profile.business_size;
  }, [profile?.business_size, empty, t]);

  const genderLabel = useMemo(() => {
    if (!profile?.gender) return empty;
    const key = GENDER_LABEL_KEY[profile.gender];
    return key ? t(key) : profile.gender;
  }, [profile?.gender, empty, t]);

  const fetchNicheSuggestions = async () => {
    setSuggestingNiches(true);
    try {
      const res = await suggestNiches();
      setNicheSuggestions(res.suggestions);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setSuggestingNiches(false);
    }
  };

  const addNiche = (raw: string) => {
    if (!draft) return;
    const cleaned = raw.trim().replace(/^#/, "");
    if (!cleaned) return;
    if (draft.niches.includes(cleaned)) return;
    if (draft.niches.length >= 7) return;
    onDraftChange({ ...draft, niches: [...draft.niches, cleaned] });
    setNicheInput("");
  };

  const removeNiche = (n: string) => {
    if (!draft) return;
    onDraftChange({ ...draft, niches: draft.niches.filter((x) => x !== n) });
  };

  if (!editing && profile) {
    return (
      <>
        {savedTick > 0 && (
          <div
            style={{
              marginBottom: 14,
              fontSize: 12.5,
              color: "var(--hot)",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <Icon name="check" size={13} /> {t("profile.editor.saved")}
          </div>
        )}
        <div className="card" style={{ padding: 28, marginBottom: 16 }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 18,
            }}
          >
            <Field
              label={t("profile.field.displayName")}
              value={profile.display_name || empty}
            />
            <Field label={t("profile.field.age")} value={ageLabel} />
            <Field label={t("profile.field.gender")} value={genderLabel} />
            <Field label={t("profile.field.business")} value={sizeLabel} />
            <Field
              label={t("profile.field.region")}
              value={profile.home_region || empty}
            />
            {profile.calendly_url && (
              <Field
                label={t("profile.field.calendly")}
                value={
                  <a
                    href={profile.calendly_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "var(--text-link)" }}
                  >
                    {profile.calendly_url}
                  </a>
                }
              />
            )}
            <Field
              label={t("profile.field.niches")}
              value={
                profile.niches && profile.niches.length > 0
                  ? profile.niches.join(", ")
                  : empty
              }
            />
          </div>
          {profile.service_description && (
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
      </>
    );
  }

  if (editing && draft) {
    return (
      <div
        className="card"
        style={{
          padding: 24,
          marginBottom: 16,
          display: "flex",
          flexDirection: "column",
          gap: 18,
        }}
      >
        <EditorField label={t("profile.field.displayName")}>
          <input
            className="input"
            value={draft.display_name}
            onChange={(e) =>
              onDraftChange({ ...draft, display_name: e.target.value })
            }
            placeholder={t("profile.field.displayNamePh")}
          />
        </EditorField>

        <EditorField label={t("profile.field.age")}>
          <ChipPicker
            options={AGE_OPTIONS.map((o) => ({
              value: o.code,
              label: t(o.labelKey),
            }))}
            value={draft.age_range}
            onChange={(v) => onDraftChange({ ...draft, age_range: v })}
          />
        </EditorField>

        <EditorField label={t("profile.field.gender")}>
          <ChipPicker
            options={GENDER_OPTIONS.map((o) => ({
              value: o.code,
              label: t(o.labelKey),
            }))}
            value={draft.gender}
            onChange={(v) => onDraftChange({ ...draft, gender: v })}
          />
        </EditorField>

        <EditorField label={t("profile.field.business")}>
          <ChipPicker
            options={SIZE_OPTIONS.map((o) => ({
              value: o.code,
              label: t(o.labelKey),
            }))}
            value={draft.business_size}
            onChange={(v) => onDraftChange({ ...draft, business_size: v })}
          />
        </EditorField>

        <EditorField label={t("profile.field.region")}>
          <input
            className="input"
            value={draft.home_region}
            onChange={(e) =>
              onDraftChange({ ...draft, home_region: e.target.value })
            }
            placeholder={t("profile.field.regionPh")}
          />
        </EditorField>

        <EditorField label={t("profile.field.calendly")}>
          <input
            className="input"
            type="url"
            value={draft.calendly_url}
            onChange={(e) =>
              onDraftChange({ ...draft, calendly_url: e.target.value })
            }
            placeholder="https://calendly.com/your-name"
          />
        </EditorField>

        <EditorField label={t("profile.field.offerRaw")}>
          <textarea
            className="textarea"
            rows={5}
            maxLength={SERVICE_DESCRIPTION_MAX}
            value={draft.service_description}
            onChange={(e) =>
              onDraftChange({
                ...draft,
                service_description: e.target.value.slice(
                  0,
                  SERVICE_DESCRIPTION_MAX,
                ),
              })
            }
            placeholder={t("profile.field.offerRawPh")}
          />
          <CharCounter
            value={draft.service_description}
            max={SERVICE_DESCRIPTION_MAX}
          />
        </EditorField>

        <EditorField label={t("profile.field.niches")}>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              className="input"
              value={nicheInput}
              onChange={(e) => setNicheInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") {
                  e.preventDefault();
                  addNiche(nicheInput);
                }
              }}
              placeholder={t("profile.field.nichesPh")}
            />
            <button
              type="button"
              className="btn"
              onClick={() => addNiche(nicheInput)}
              disabled={!nicheInput.trim() || draft.niches.length >= 7}
            >
              <Icon name="plus" size={14} />
            </button>
          </div>

          {(profile?.service_description || profile?.profession) &&
            draft.niches.length < 7 && (
              <div style={{ marginTop: 10 }}>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={fetchNicheSuggestions}
                  disabled={suggestingNiches}
                >
                  <Icon name="sparkles" size={13} />
                  {suggestingNiches
                    ? t("common.loading")
                    : nicheSuggestions === null
                      ? t("profile.niches.suggest")
                      : t("profile.niches.suggestAgain")}
                </button>
                {nicheSuggestions !== null &&
                  nicheSuggestions.length === 0 && (
                    <div
                      style={{
                        marginTop: 8,
                        fontSize: 12,
                        color: "var(--text-dim)",
                      }}
                    >
                      {t("profile.niches.suggestEmpty")}
                    </div>
                  )}
                {nicheSuggestions && nicheSuggestions.length > 0 && (
                  <div
                    style={{
                      marginTop: 8,
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 6,
                    }}
                  >
                    {nicheSuggestions
                      .filter(
                        (s) =>
                          !draft.niches
                            .map((n) => n.toLowerCase())
                            .includes(s.toLowerCase()),
                      )
                      .map((s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => {
                            addNiche(s);
                            setNicheSuggestions((prev) =>
                              prev
                                ? prev.filter(
                                    (x) =>
                                      x.toLowerCase() !== s.toLowerCase(),
                                  )
                                : prev,
                            );
                          }}
                          disabled={draft.niches.length >= 7}
                          style={{
                            padding: "6px 11px",
                            fontSize: 12,
                            borderRadius: 999,
                            cursor: "pointer",
                            border:
                              "1px solid color-mix(in srgb, var(--accent) 30%, var(--border))",
                            background:
                              "color-mix(in srgb, var(--accent) 8%, var(--surface))",
                            color: "var(--accent)",
                            fontWeight: 600,
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 4,
                          }}
                        >
                          <Icon name="plus" size={11} />
                          {s}
                        </button>
                      ))}
                  </div>
                )}
              </div>
            )}

          {draft.niches.length > 0 && (
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
                marginTop: 12,
              }}
            >
              {draft.niches.map((n) => (
                <span
                  key={n}
                  className="chip"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    cursor: "pointer",
                  }}
                  onClick={() => removeNiche(n)}
                >
                  {n}
                  <Icon name="x" size={12} />
                </span>
              ))}
            </div>
          )}
        </EditorField>
      </div>
    );
  }

  return null;
}

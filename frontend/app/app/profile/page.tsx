"use client";

import { useEffect, useMemo, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  getMyProfile,
  updateMyProfile,
  type UserProfile,
  type UserProfileUpdate,
} from "@/lib/api";
import { setOnboarded } from "@/lib/auth";
import { useLocale, type TranslationKey } from "@/lib/i18n";

const AGE_OPTIONS: { code: string; labelKey: TranslationKey }[] = [
  { code: "<18", labelKey: "onboarding.age.lt18" },
  { code: "18-24", labelKey: "onboarding.age.18_24" },
  { code: "25-34", labelKey: "onboarding.age.25_34" },
  { code: "35-44", labelKey: "onboarding.age.35_44" },
  { code: "45-54", labelKey: "onboarding.age.45_54" },
  { code: "55+", labelKey: "onboarding.age.55plus" },
];

const SIZE_OPTIONS: { code: string; labelKey: TranslationKey }[] = [
  { code: "solo", labelKey: "onboarding.size.solo" },
  { code: "small", labelKey: "onboarding.size.small" },
  { code: "medium", labelKey: "onboarding.size.medium" },
  { code: "large", labelKey: "onboarding.size.large" },
];

const AGE_LABEL_KEY: Record<string, TranslationKey> = Object.fromEntries(
  AGE_OPTIONS.map((o) => [o.code, o.labelKey]),
);

const SIZE_LABEL_KEY: Record<string, TranslationKey> = Object.fromEntries(
  SIZE_OPTIONS.map((o) => [o.code, o.labelKey]),
);

interface DraftState {
  display_name: string;
  age_range: string | null;
  business_size: string | null;
  service_description: string;
  home_region: string;
  niches: string[];
}

function profileToDraft(p: UserProfile): DraftState {
  return {
    display_name: p.display_name ?? "",
    age_range: p.age_range,
    business_size: p.business_size,
    service_description: p.service_description ?? "",
    home_region: p.home_region ?? "",
    niches: p.niches ?? [],
  };
}

export default function ProfilePage() {
  const { t } = useLocale();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedTick, setSavedTick] = useState(0);
  const [nicheInput, setNicheInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMyProfile()
      .then((p) => {
        setProfile(p);
        setOnboarded(p.onboarded);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

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

  const startEdit = () => {
    if (!profile) return;
    setDraft(profileToDraft(profile));
    setNicheInput("");
    setError(null);
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft(null);
    setNicheInput("");
    setError(null);
  };

  const askHenry = () => {
    if (typeof window === "undefined") return;
    window.dispatchEvent(new CustomEvent("convioo:open-henry"));
  };

  const addNiche = (raw: string) => {
    if (!draft) return;
    const cleaned = raw.trim().replace(/^#/, "");
    if (!cleaned) return;
    if (draft.niches.includes(cleaned)) return;
    if (draft.niches.length >= 7) return;
    setDraft({ ...draft, niches: [...draft.niches, cleaned] });
    setNicheInput("");
  };

  const removeNiche = (n: string) => {
    if (!draft) return;
    setDraft({ ...draft, niches: draft.niches.filter((x) => x !== n) });
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const patch: UserProfileUpdate = {
        display_name: draft.display_name.trim() || null,
        age_range: draft.age_range,
        business_size: draft.business_size,
        service_description: draft.service_description.trim() || null,
        home_region: draft.home_region.trim() || null,
        niches: draft.niches,
      };
      const updated = await updateMyProfile(patch);
      setProfile(updated);
      setOnboarded(updated.onboarded);
      setEditing(false);
      setDraft(null);
      setNicheInput("");
      setSavedTick(Date.now());
    } catch (e) {
      const detail =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e);
      setError(detail);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Topbar
        title={t("profile.title")}
        subtitle={
          editing ? t("profile.editor.subtitle") : t("profile.subtitle")
        }
        right={
          editing ? (
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={cancelEdit}
                disabled={saving}
              >
                {t("profile.editor.cancel")}
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={save}
                disabled={saving}
              >
                {saving ? t("profile.editor.saving") : t("profile.editor.save")}{" "}
                <Icon name="check" size={13} />
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={askHenry}
              >
                <Icon name="sparkles" size={13} />
                {t("profile.editor.askHenry")}
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={startEdit}
                disabled={!profile}
              >
                <Icon name="pencil" size={13} /> {t("common.edit")}
              </button>
            </div>
          )
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

        {!editing && profile && savedTick > 0 && (
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

        {!editing && profile && (
          <div className="card" style={{ padding: 28, marginBottom: 16 }}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 18,
              }}
            >
              <Field label={t("profile.field.business")} value={sizeLabel} />
              <Field
                label={t("profile.field.region")}
                value={profile.home_region || empty}
              />
              <Field
                label={t("profile.field.offer")}
                value={profile.profession || empty}
              />
              <Field
                label={t("profile.field.niches")}
                value={
                  profile.niches && profile.niches.length > 0
                    ? profile.niches.join(", ")
                    : empty
                }
              />
              <Field label={t("profile.field.age")} value={ageLabel} />
              <Field
                label={t("profile.field.displayName")}
                value={profile.display_name || empty}
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
        )}

        {editing && draft && (
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
                  setDraft({ ...draft, display_name: e.target.value })
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
                onChange={(v) => setDraft({ ...draft, age_range: v })}
              />
            </EditorField>

            <EditorField label={t("profile.field.business")}>
              <ChipPicker
                options={SIZE_OPTIONS.map((o) => ({
                  value: o.code,
                  label: t(o.labelKey),
                }))}
                value={draft.business_size}
                onChange={(v) => setDraft({ ...draft, business_size: v })}
              />
            </EditorField>

            <EditorField label={t("profile.field.region")}>
              <input
                className="input"
                value={draft.home_region}
                onChange={(e) =>
                  setDraft({ ...draft, home_region: e.target.value })
                }
                placeholder={t("profile.field.regionPh")}
              />
            </EditorField>

            <EditorField label={t("profile.field.offerRaw")}>
              <textarea
                className="textarea"
                rows={5}
                value={draft.service_description}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    service_description: e.target.value,
                  })
                }
                placeholder={t("profile.field.offerRawPh")}
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
        )}

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

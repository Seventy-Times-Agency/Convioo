"use client";

import React, { useState } from "react";
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
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";
import { useEffect } from "react";
import {
  ProfileFormSection,
  profileToDraft,
  SERVICE_DESCRIPTION_MAX,
  type DraftState,
} from "@/components/settings/ProfileFormSection";
import { HenryMemorySection } from "@/components/settings/HenryMemorySection";
import { PrivacyDataSection } from "@/components/settings/PrivacyDataSection";

export default function ProfilePage() {
  const { t } = useLocale();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedTick, setSavedTick] = useState(0);

  useEffect(() => {
    getMyProfile()
      .then((p) => {
        setProfile(p);
        setOnboarded(p.onboarded);
      })
      .catch((e) => showError(e instanceof Error ? e.message : String(e)));
  }, []);

  const startEdit = () => {
    if (!profile) return;
    setDraft(profileToDraft(profile));
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft(null);
  };

  const askHenry = () => {
    if (typeof window === "undefined") return;
    window.dispatchEvent(new CustomEvent("convioo:open-henry"));
  };

  const save = async () => {
    if (!draft) return;
    // Pre-flight: catch the only common length problem on the client
    // so the user gets a friendly message instead of a 422 round-trip.
    if (draft.service_description.length > SERVICE_DESCRIPTION_MAX) {
      showError(
        t("profile.editor.tooLong", {
          field: t("profile.field.offerRaw"),
          max: SERVICE_DESCRIPTION_MAX,
        }),
      );
      return;
    }
    setSaving(true);
    try {
      const patch: UserProfileUpdate = {
        display_name: draft.display_name.trim() || null,
        age_range: draft.age_range,
        gender: draft.gender,
        business_size: draft.business_size,
        service_description: draft.service_description.trim() || null,
        home_region: draft.home_region.trim() || null,
        niches: draft.niches,
        calendly_url: draft.calendly_url.trim() || null,
      };
      const updated = await updateMyProfile(patch);
      setProfile(updated);
      setOnboarded(updated.onboarded);
      setEditing(false);
      setDraft(null);
      setSavedTick(Date.now());
    } catch (e) {
      // Translate Pydantic / DB length errors into a one-line "это
      // поле слишком длинное" so the user sees something actionable
      // instead of "value too long for type character varying".
      let detail =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e);
      if (
        e instanceof ApiError &&
        (e.status === 422 || /too long|string_too_long|character varying/i.test(detail))
      ) {
        detail = t("profile.editor.tooLong", {
          field: t("profile.field.offerRaw"),
          max: SERVICE_DESCRIPTION_MAX,
        });
      }
      showError(detail);
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
        <ProfileFormSection
          profile={profile}
          editing={editing}
          draft={draft}
          savedTick={savedTick}
          onDraftChange={setDraft}
        />

        <HenryMemorySection />

        <PrivacyDataSection />

        <div
          className="card"
          style={{ padding: 20, background: "var(--surface-2)", marginTop: 16 }}
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

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  getMyProfile,
  updateMyProfile,
  type UserProfile,
} from "@/lib/api";
import {
  getCurrentUser,
  setCurrentUser,
  setOnboarded,
  type CurrentUser,
} from "@/lib/auth";
import { useLocale, type TranslationKey } from "@/lib/i18n";

interface AgeOption {
  code: string;
  labelKey: TranslationKey;
}

interface SizeOption {
  code: string;
  labelKey: TranslationKey;
}

const AGE_OPTIONS: AgeOption[] = [
  { code: "<18", labelKey: "onboarding.age.lt18" },
  { code: "18-24", labelKey: "onboarding.age.18_24" },
  { code: "25-34", labelKey: "onboarding.age.25_34" },
  { code: "35-44", labelKey: "onboarding.age.35_44" },
  { code: "45-54", labelKey: "onboarding.age.45_54" },
  { code: "55+", labelKey: "onboarding.age.55plus" },
];

const SIZE_OPTIONS: SizeOption[] = [
  { code: "solo", labelKey: "onboarding.size.solo" },
  { code: "small", labelKey: "onboarding.size.small" },
  { code: "medium", labelKey: "onboarding.size.medium" },
  { code: "large", labelKey: "onboarding.size.large" },
];

interface DraftState {
  display_name: string;
  age_range: string | null;
  business_size: string | null;
  service_description: string;
  home_region: string;
  niches: string[];
}

const TOTAL_STEPS = 6;

export default function OnboardingPage() {
  const router = useRouter();
  const { t } = useLocale();
  const [user, setUser] = useState<CurrentUser | null | "loading">("loading");
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftState>({
    display_name: "",
    age_range: null,
    business_size: null,
    service_description: "",
    home_region: "",
    niches: [],
  });
  const [niche, setNicheInput] = useState("");

  useEffect(() => {
    const u = getCurrentUser();
    if (!u) {
      router.replace("/login");
      setUser(null);
      return;
    }
    setUser(u);
    getMyProfile(u.user_id)
      .then((profile) => {
        if (profile.onboarded) {
          setOnboarded(true);
          router.replace("/app");
          return;
        }
        const fallbackName =
          profile.display_name ||
          [profile.first_name, profile.last_name].filter(Boolean).join(" ");
        setDraft({
          display_name: fallbackName,
          age_range: profile.age_range,
          business_size: profile.business_size,
          service_description: profile.service_description ?? "",
          home_region: profile.home_region ?? "",
          niches: profile.niches ?? [],
        });
      })
      .catch(() => {
        // Profile load failure is non-fatal — onboarding can still proceed.
      });
  }, [router]);

  if (user === "loading" || user === null) return null;

  const goNext = () => setStep((s) => Math.min(s + 1, TOTAL_STEPS - 1));
  const goPrev = () => setStep((s) => Math.max(s - 1, 0));

  const addNiche = (raw: string) => {
    const cleaned = raw.trim().replace(/^#/, "");
    if (!cleaned) return;
    if (draft.niches.includes(cleaned)) return;
    if (draft.niches.length >= 7) return;
    setDraft((d) => ({ ...d, niches: [...d.niches, cleaned] }));
    setNicheInput("");
  };

  const removeNiche = (n: string) => {
    setDraft((d) => ({ ...d, niches: d.niches.filter((x) => x !== n) }));
  };

  const stepValid = (): boolean => {
    switch (step) {
      case 0:
        return draft.display_name.trim().length >= 2;
      case 1:
      case 2:
        return true; // optional, may be null
      case 3:
        return draft.service_description.trim().length >= 5;
      case 4:
        return draft.home_region.trim().length >= 2;
      case 5:
        return draft.niches.length >= 3 && draft.niches.length <= 7;
      default:
        return false;
    }
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await updateMyProfile({
        display_name: draft.display_name.trim(),
        age_range: draft.age_range,
        business_size: draft.business_size,
        service_description: draft.service_description.trim(),
        home_region: draft.home_region.trim(),
        niches: draft.niches,
      });
      setOnboarded(true);
      router.push("/app");
    } catch (e) {
      const detail =
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(detail);
      setSubmitting(false);
    }
  };

  const stepTitle = t(`onboarding.step.${step}.title` as TranslationKey);
  const stepHelp = t(`onboarding.step.${step}.help` as TranslationKey);
  const isLast = step === TOTAL_STEPS - 1;

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: "40px 20px",
        background: "var(--bg)",
      }}
    >
      <div style={{ width: "100%", maxWidth: 520 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            marginBottom: 24,
          }}
        >
          {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
            <div
              key={i}
              style={{
                flex: 1,
                height: 4,
                borderRadius: 2,
                background:
                  i <= step ? "var(--accent)" : "var(--surface-2)",
                transition: "background .25s",
              }}
            />
          ))}
        </div>

        <div className="eyebrow" style={{ marginBottom: 6 }}>
          {t("onboarding.eyebrow", { step: step + 1, total: TOTAL_STEPS })}
        </div>
        <h1
          style={{
            fontSize: 32,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            lineHeight: 1.1,
            margin: "0 0 10px",
          }}
        >
          {stepTitle}
        </h1>
        <p
          style={{
            color: "var(--text-muted)",
            fontSize: 14.5,
            lineHeight: 1.55,
            margin: "0 0 24px",
          }}
        >
          {stepHelp}
        </p>

        <div className="card" style={{ padding: 22 }}>
          {step === 0 && (
            <input
              className="input"
              autoFocus
              placeholder={t("onboarding.step.0.ph")}
              value={draft.display_name}
              onChange={(e) =>
                setDraft((d) => ({ ...d, display_name: e.target.value }))
              }
            />
          )}

          {step === 1 && (
            <ChipPicker
              options={AGE_OPTIONS.map((o) => ({
                value: o.code,
                label: t(o.labelKey),
              }))}
              value={draft.age_range}
              onChange={(v) => setDraft((d) => ({ ...d, age_range: v }))}
              skipLabel={t("onboarding.skip")}
            />
          )}

          {step === 2 && (
            <ChipPicker
              options={SIZE_OPTIONS.map((o) => ({
                value: o.code,
                label: t(o.labelKey),
              }))}
              value={draft.business_size}
              onChange={(v) => setDraft((d) => ({ ...d, business_size: v }))}
              skipLabel={t("onboarding.skip")}
            />
          )}

          {step === 3 && (
            <textarea
              className="textarea"
              rows={5}
              autoFocus
              placeholder={t("onboarding.step.3.ph")}
              value={draft.service_description}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  service_description: e.target.value,
                }))
              }
            />
          )}

          {step === 4 && (
            <input
              className="input"
              autoFocus
              placeholder={t("onboarding.step.4.ph")}
              value={draft.home_region}
              onChange={(e) =>
                setDraft((d) => ({ ...d, home_region: e.target.value }))
              }
            />
          )}

          {step === 5 && (
            <div>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  className="input"
                  autoFocus
                  placeholder={t("onboarding.step.5.ph")}
                  value={niche}
                  onChange={(e) => setNicheInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === ",") {
                      e.preventDefault();
                      addNiche(niche);
                    }
                  }}
                />
                <button
                  type="button"
                  className="btn"
                  onClick={() => addNiche(niche)}
                  disabled={!niche.trim() || draft.niches.length >= 7}
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
                    marginTop: 14,
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
              <div
                style={{
                  marginTop: 12,
                  fontSize: 12,
                  color: "var(--text-dim)",
                }}
              >
                {t("onboarding.step.5.counter", {
                  n: draft.niches.length,
                })}
              </div>
            </div>
          )}

          {error && (
            <div style={{ marginTop: 14, fontSize: 13, color: "var(--cold)" }}>
              {error}
            </div>
          )}
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 18,
          }}
        >
          <button
            type="button"
            className="btn btn-ghost"
            onClick={goPrev}
            disabled={step === 0 || submitting}
            style={{ visibility: step === 0 ? "hidden" : "visible" }}
          >
            <Icon name="arrow" size={14} style={{ transform: "rotate(180deg)" }} />
            {t("common.back")}
          </button>
          {isLast ? (
            <button
              type="button"
              className="btn btn-lg"
              onClick={submit}
              disabled={!stepValid() || submitting}
              style={{ opacity: !stepValid() || submitting ? 0.5 : 1 }}
            >
              {submitting ? t("common.loading") : t("onboarding.finish")}{" "}
              <Icon name="check" size={15} />
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-lg"
              onClick={goNext}
              disabled={!stepValid()}
              style={{ opacity: !stepValid() ? 0.5 : 1 }}
            >
              {t("onboarding.next")} <Icon name="arrow" size={15} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ChipPicker({
  options,
  value,
  onChange,
  skipLabel,
}: {
  options: { value: string; label: string }[];
  value: string | null;
  onChange: (v: string | null) => void;
  skipLabel: string;
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={
            "chip" + (value === o.value ? " chip-active" : "")
          }
          style={{
            padding: "8px 14px",
            fontSize: 13.5,
            cursor: "pointer",
            border:
              value === o.value
                ? "1px solid var(--accent)"
                : "1px solid var(--border)",
            background:
              value === o.value
                ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                : "var(--surface)",
            color: value === o.value ? "var(--accent)" : "var(--text)",
          }}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
      <button
        type="button"
        className="chip"
        style={{
          padding: "8px 14px",
          fontSize: 13.5,
          cursor: "pointer",
          color: "var(--text-dim)",
        }}
        onClick={() => onChange(null)}
      >
        {skipLabel}
      </button>
    </div>
  );
}

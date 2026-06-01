"use client";

import {
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";
import Link from "next/link";
import { Icon, type IconName } from "@/components/Icon";
import { NicheCombobox } from "@/components/app/NicheCombobox";
import { RegionCombobox } from "@/components/app/RegionCombobox";
import { SuggestAxesPanel } from "./SuggestAxesPanel";
import { useLocale } from "@/lib/i18n";
import {
  LEAD_LIMIT_CHOICES,
  RADIUS_CHOICES_KM,
  SEARCH_SCOPES,
  type LeadLimitChoice,
  type PriorTeamSearch,
  type RadiusChoiceKm,
  type SearchAxisOption,
  type SearchScope,
  type SearchSource,
  type UserProfile,
} from "@/lib/api";
import type { OfferSource } from "./types";

const LANGUAGE_OPTIONS = [
  { code: "ru", labelKey: "search.lang.ru" as const },
  { code: "uk", labelKey: "search.lang.uk" as const },
  { code: "en", labelKey: "search.lang.en" as const },
  { code: "de", labelKey: "search.lang.de" as const },
  { code: "es", labelKey: "search.lang.es" as const },
  { code: "fr", labelKey: "search.lang.fr" as const },
  { code: "pl", labelKey: "search.lang.pl" as const },
];

function SourceTab({
  label,
  active,
  disabled,
  onClick,
}: {
  label: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "7px 13px",
        fontSize: 12.5,
        fontWeight: active ? 600 : 500,
        borderRadius: 999,
        cursor: disabled ? "not-allowed" : "pointer",
        border: active
          ? "1px solid var(--accent)"
          : "1px solid var(--border)",
        background: active
          ? "color-mix(in srgb, var(--accent) 14%, transparent)"
          : "var(--surface-2)",
        color: disabled
          ? "var(--text-dim)"
          : active
            ? "var(--accent)"
            : "var(--text)",
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {label}
    </button>
  );
}

function FormCard({
  icon,
  label,
  hint,
  required,
  flashKey,
  children,
}: {
  icon: IconName;
  label: string;
  hint?: string;
  required?: boolean;
  flashKey?: number;
  children: React.ReactNode;
}) {
  const [flashClass, setFlashClass] = useState("");
  useEffect(() => {
    if (!flashKey) return;
    setFlashClass("lumen-touched");
    const id = setTimeout(() => setFlashClass(""), 1300);
    return () => clearTimeout(id);
  }, [flashKey]);

  const cardStyle: CSSProperties = {
    padding: 14,
    borderRadius: 12,
    border: "1px solid var(--border)",
    background: "var(--surface)",
    display: "flex",
    flexDirection: "column",
    gap: 10,
  };

  return (
    <div className={flashClass} style={cardStyle}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <div
          style={{
            width: 24,
            height: 24,
            borderRadius: 6,
            background: "var(--surface-2)",
            display: "grid",
            placeItems: "center",
            color: "var(--text-muted)",
            flexShrink: 0,
          }}
        >
          <Icon name={icon} size={13} />
        </div>
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            letterSpacing: "-0.005em",
          }}
        >
          {label}
        </div>
        {required && (
          <span
            style={{
              fontSize: 10,
              color: "var(--accent)",
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            ·
          </span>
        )}
        {hint && (
          <span
            style={{
              marginLeft: "auto",
              fontSize: 11,
              color: "var(--text-dim)",
            }}
          >
            {hint}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

export function FormColumn({
  niche,
  region,
  idealCustomer,
  exclusions,
  profession,
  targetLanguages,
  aiTouched,
  profile,
  offerSource,
  onOfferSourceChange,
  onNicheChange,
  onRegionChange,
  onIdealCustomerChange,
  onExclusionsChange,
  onProfessionChange,
  onTargetLanguagesChange,
  leadLimit,
  onLeadLimitChange,
  scope,
  onScopeChange,
  radiusKm,
  onRadiusKmChange,
  enabledSources,
  onToggleSource,
  readyHint,
  onLaunch,
  launching,
  launchDisabled,
  submitError,
  duplicateMatches,
  axesOptions,
  axesLoading,
  axesError,
  onFetchAxes,
  onApplyAxis,
  onDismissAxes,
}: {
  niche: string;
  region: string;
  idealCustomer: string;
  exclusions: string;
  profession: string;
  targetLanguages: string[];
  aiTouched: Record<string, number>;
  profile: UserProfile | null;
  offerSource: OfferSource;
  onOfferSourceChange: (v: OfferSource) => void;
  onNicheChange: (v: string) => void;
  onRegionChange: (v: string) => void;
  onIdealCustomerChange: (v: string) => void;
  onExclusionsChange: (v: string) => void;
  onProfessionChange: (v: string) => void;
  onTargetLanguagesChange: (v: string[]) => void;
  leadLimit: LeadLimitChoice;
  onLeadLimitChange: (v: LeadLimitChoice) => void;
  scope: SearchScope;
  onScopeChange: (v: SearchScope) => void;
  radiusKm: RadiusChoiceKm;
  onRadiusKmChange: (v: RadiusChoiceKm) => void;
  enabledSources: Set<SearchSource>;
  onToggleSource: (src: SearchSource) => void;
  readyHint: boolean;
  onLaunch: () => void;
  launching: boolean;
  launchDisabled: boolean;
  submitError: string | null;
  duplicateMatches: PriorTeamSearch[];
  axesOptions: SearchAxisOption[] | null;
  axesLoading: boolean;
  axesError: string | null;
  onFetchAxes: () => void;
  onApplyAxis: (opt: SearchAxisOption) => void;
  onDismissAxes: () => void;
}) {
  const { t } = useLocale();

  const profileOffer =
    (profile?.service_description?.trim() ||
      profile?.profession?.trim() ||
      "") ?? "";
  const profileHasOffer = profileOffer.length > 0;

  const filledCount = useMemo(() => {
    let n = 0;
    if (niche.trim()) n++;
    if (region.trim()) n++;
    if (idealCustomer.trim()) n++;
    if (exclusions.trim()) n++;
    if (targetLanguages.length > 0) n++;
    const offerFilled =
      offerSource === "profile" ? profileHasOffer : profession.trim().length > 0;
    if (offerFilled) n++;
    return n;
  }, [
    niche,
    region,
    idealCustomer,
    exclusions,
    targetLanguages,
    profession,
    offerSource,
    profileHasOffer,
  ]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <style>{`
        @keyframes lumen-pulse {
          0%, 80%, 100% { opacity: 0.35; transform: scale(.85); }
          40% { opacity: 1; transform: scale(1); }
        }
        @keyframes lumen-flash {
          0% { background: color-mix(in srgb, var(--accent) 18%, transparent); }
          100% { background: var(--surface); }
        }
        .lumen-touched {
          animation: lumen-flash 1.2s ease-out;
        }
      `}</style>

      <div>
        <div
          className="eyebrow"
          style={{
            marginBottom: 4,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <span>{t("search.form.eyebrow")}</span>
          <span style={{ color: "var(--text-dim)", fontWeight: 500 }}>
            · {filledCount}/6
          </span>
        </div>
        <div
          style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: "-0.01em",
            marginBottom: 4,
          }}
        >
          {t("search.form.title")}
        </div>
        <div
          style={{
            fontSize: 13,
            color: "var(--text-muted)",
            lineHeight: 1.5,
          }}
        >
          {t("search.form.subtitle")}
        </div>
      </div>

      <SuggestAxesPanel
        profile={profile}
        loading={axesLoading}
        options={axesOptions}
        error={axesError}
        onFetch={onFetchAxes}
        onApply={onApplyAxis}
        onDismiss={onDismissAxes}
      />

      <FormCard
        icon="folder"
        label={t("search.form.niche")}
        hint={t("search.form.nicheHint")}
        required
        flashKey={aiTouched.niche}
      >
        <NicheCombobox
          value={niche}
          onChange={onNicheChange}
          placeholder={t("search.form.nichePh")}
          language={profile?.language_code ?? undefined}
        />
      </FormCard>

      <FormCard
        icon="mapPin"
        label={t("search.form.region")}
        hint={t("search.form.regionHint")}
        required
        flashKey={aiTouched.region}
      >
        <RegionCombobox
          value={region}
          onChange={onRegionChange}
          placeholder={t("search.form.regionPh")}
          language={profile?.language_code ?? undefined}
        />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
          {SEARCH_SCOPES.map((s) => {
            const active = scope === s;
            const labels: Record<SearchScope, string> = {
              city: t("search.scope.city"),
              metro: t("search.scope.metro"),
              state: t("search.scope.state"),
              country: t("search.scope.country"),
            };
            return (
              <button
                key={s}
                type="button"
                onClick={() => onScopeChange(s)}
                style={{
                  padding: "5px 11px",
                  fontSize: 12,
                  borderRadius: 999,
                  cursor: "pointer",
                  border: active
                    ? "1px solid var(--accent)"
                    : "1px solid var(--border)",
                  background: active
                    ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                    : "var(--surface-2)",
                  color: active ? "var(--accent)" : "var(--text)",
                  fontWeight: active ? 600 : 500,
                }}
              >
                {labels[s]}
              </button>
            );
          })}
        </div>
        {(scope === "city" || scope === "metro") && (
          <div style={{ marginTop: 10 }}>
            <div
              className="eyebrow"
              style={{ fontSize: 10, marginBottom: 6 }}
            >
              {t("search.radius.label", { km: radiusKm })}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {RADIUS_CHOICES_KM.map((r) => {
                const active = radiusKm === r;
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => onRadiusKmChange(r)}
                    style={{
                      padding: "4px 10px",
                      fontSize: 12,
                      borderRadius: 999,
                      cursor: "pointer",
                      border: active
                        ? "1px solid var(--accent)"
                        : "1px solid var(--border)",
                      background: active
                        ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                        : "var(--surface-2)",
                      color: active ? "var(--accent)" : "var(--text)",
                      fontWeight: active ? 600 : 500,
                      minWidth: 44,
                    }}
                  >
                    {t("search.radius.km", { km: r })}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </FormCard>

      <FormCard
        icon="users"
        label={t("search.form.ideal")}
        hint={t("search.form.idealHint")}
        flashKey={aiTouched.ideal_customer}
      >
        <textarea
          className="textarea"
          rows={2}
          value={idealCustomer}
          onChange={(e) => onIdealCustomerChange(e.target.value)}
          placeholder={t("search.form.idealPh")}
        />
      </FormCard>

      <FormCard
        icon="x"
        label={t("search.form.exclude")}
        hint={t("search.form.excludeHint")}
        flashKey={aiTouched.exclusions}
      >
        <input
          className="input"
          value={exclusions}
          onChange={(e) => onExclusionsChange(e.target.value)}
          placeholder={t("search.form.excludePh")}
        />
      </FormCard>

      <FormCard
        icon="globe"
        label={t("search.form.lang")}
        hint={t("search.form.langHint")}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {LANGUAGE_OPTIONS.map((opt) => {
            const active = targetLanguages.includes(opt.code);
            return (
              <button
                key={opt.code}
                type="button"
                onClick={() => {
                  onTargetLanguagesChange(
                    active
                      ? targetLanguages.filter((c) => c !== opt.code)
                      : [...targetLanguages, opt.code],
                  );
                }}
                style={{
                  padding: "6px 12px",
                  fontSize: 12.5,
                  borderRadius: 999,
                  cursor: "pointer",
                  border: active
                    ? "1px solid var(--accent)"
                    : "1px solid var(--border)",
                  background: active
                    ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                    : "var(--surface-2)",
                  color: active ? "var(--accent)" : "var(--text)",
                  fontWeight: active ? 600 : 500,
                }}
              >
                {t(opt.labelKey)}
              </button>
            );
          })}
        </div>
        <div
          style={{
            fontSize: 11.5,
            color: "var(--text-dim)",
            marginTop: 8,
            lineHeight: 1.45,
          }}
        >
          {t("search.form.langHelp")}
        </div>
      </FormCard>

      <FormCard
        icon="filter"
        label={t("search.form.leadCount")}
        hint={t("search.form.leadCountHint")}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {LEAD_LIMIT_CHOICES.map((n) => {
            const active = leadLimit === n;
            return (
              <button
                key={n}
                type="button"
                onClick={() => onLeadLimitChange(n)}
                style={{
                  padding: "6px 14px",
                  fontSize: 13,
                  borderRadius: 999,
                  cursor: "pointer",
                  border: active
                    ? "1px solid var(--accent)"
                    : "1px solid var(--border)",
                  background: active
                    ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                    : "var(--surface-2)",
                  color: active ? "var(--accent)" : "var(--text)",
                  fontWeight: active ? 600 : 500,
                  minWidth: 44,
                }}
              >
                {n}
              </button>
            );
          })}
        </div>
        <div
          style={{
            fontSize: 11.5,
            color: "var(--text-dim)",
            marginTop: 8,
            lineHeight: 1.45,
          }}
        >
          {t("search.form.leadCountHelp")}
        </div>
      </FormCard>

      <FormCard
        icon="filter"
        label={t("search.form.sources")}
        hint={t("search.form.sourcesHint")}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {(
            [
              { id: "google" as SearchSource, label: "Google Places" },
              { id: "osm" as SearchSource, label: "OpenStreetMap" },
              { id: "yelp" as SearchSource, label: "Yelp" },
              { id: "foursquare" as SearchSource, label: "Foursquare" },
            ]
          ).map((src) => {
            const checked = enabledSources.has(src.id);
            return (
              <label
                key={src.id}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 12px",
                  fontSize: 13,
                  borderRadius: 999,
                  cursor: "pointer",
                  border: checked
                    ? "1px solid var(--accent)"
                    : "1px solid var(--border)",
                  background: checked
                    ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                    : "var(--surface-2)",
                  color: checked ? "var(--accent)" : "var(--text-muted)",
                  fontWeight: checked ? 600 : 500,
                  userSelect: "none",
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggleSource(src.id)}
                  style={{ accentColor: "var(--accent)" }}
                />
                {src.label}
              </label>
            );
          })}
        </div>
        <div
          style={{
            fontSize: 11.5,
            color: "var(--text-dim)",
            marginTop: 8,
            lineHeight: 1.45,
          }}
        >
          {t("search.form.sourcesHelp")}
        </div>
      </FormCard>

      <FormCard
        icon="briefcase"
        label={t("search.form.offer")}
        hint={t("search.form.offerHint")}
      >
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <SourceTab
            label={t("search.form.offerSource.profile")}
            active={offerSource === "profile"}
            disabled={!profileHasOffer}
            onClick={() => onOfferSourceChange("profile")}
          />
          <SourceTab
            label={t("search.form.offerSource.custom")}
            active={offerSource === "custom"}
            onClick={() => onOfferSourceChange("custom")}
          />
        </div>
        {offerSource === "profile" ? (
          profileHasOffer ? (
            <div
              style={{
                marginTop: 4,
                padding: "11px 13px",
                borderRadius: 10,
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                fontSize: 13,
                lineHeight: 1.55,
                color: "var(--text)",
                whiteSpace: "pre-wrap",
              }}
            >
              {profileOffer}
            </div>
          ) : (
            <div
              style={{
                marginTop: 4,
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              {t("search.form.offerSource.profileEmpty")}{" "}
              <Link
                href="/app/profile"
                style={{ color: "var(--accent)", fontWeight: 600 }}
              >
                {t("search.form.offerSource.profileLink")}
              </Link>
            </div>
          )
        ) : (
          <>
            <textarea
              className="textarea"
              rows={3}
              value={profession}
              onChange={(e) => onProfessionChange(e.target.value)}
              placeholder={t("search.form.offerPh")}
            />
            {!profileHasOffer && (
              <div
                style={{
                  fontSize: 11.5,
                  color: "var(--text-dim)",
                  lineHeight: 1.45,
                }}
              >
                {t("search.form.offerSource.empty")}
              </div>
            )}
          </>
        )}
      </FormCard>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "12px 14px",
          background: "var(--surface-2)",
          borderRadius: 10,
          border: "1px solid var(--border)",
          fontSize: 12.5,
          color: "var(--text-muted)",
        }}
      >
        <Icon name="zap" size={16} style={{ color: "var(--warm)" }} />
        <div style={{ flex: 1 }}>{t("search.form.meta")}</div>
      </div>

      {duplicateMatches.length > 0 && (
        <div
          style={{
            padding: "14px 16px",
            border:
              "1px solid color-mix(in srgb, var(--cold) 35%, var(--border))",
            background: "color-mix(in srgb, var(--cold) 6%, var(--surface))",
            borderRadius: 12,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              color: "var(--cold)",
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            <Icon name="x" size={14} />
            {t("search.preflight.title")}
          </div>
          <div
            style={{
              fontSize: 12.5,
              color: "var(--text-muted)",
              lineHeight: 1.5,
            }}
          >
            {t("search.preflight.body")}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {duplicateMatches.slice(0, 3).map((m) => (
              <div
                key={m.search_id}
                style={{
                  fontSize: 12,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  color: "var(--text)",
                }}
              >
                <span style={{ fontWeight: 600 }}>{m.user_name}</span>
                <span style={{ color: "var(--text-dim)" }}>·</span>
                <span style={{ color: "var(--text-muted)" }}>
                  {new Date(m.created_at).toLocaleDateString()}
                </span>
                <span style={{ color: "var(--text-dim)" }}>·</span>
                <span style={{ color: "var(--text-muted)" }}>
                  {t("search.preflight.leadsCount", { n: m.leads_count })}
                </span>
                <Link
                  href={`/app/sessions/${m.search_id}`}
                  style={{
                    marginLeft: "auto",
                    color: "var(--accent)",
                    fontSize: 11.5,
                  }}
                >
                  {t("search.preflight.openSession")}
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}

      {submitError && (
        <div style={{ fontSize: 13, color: "var(--cold)" }}>{submitError}</div>
      )}

      <button
        type="button"
        className="btn btn-lg"
        disabled={launchDisabled}
        onClick={onLaunch}
        style={{
          justifyContent: "center",
          opacity: launchDisabled ? 0.5 : 1,
          background: readyHint
            ? "linear-gradient(135deg, var(--accent), #EC4899)"
            : undefined,
          color: readyHint ? "white" : undefined,
          border: readyHint ? "none" : undefined,
        }}
      >
        <Icon name="sparkles" size={16} />
        {launching ? t("common.loading") : t("search.form.launch")}
      </button>
    </div>
  );
}

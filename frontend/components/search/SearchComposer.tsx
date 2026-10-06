"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import { Icon, type IconName } from "@/components/brand/Icon";
import { NicheCombobox } from "@/components/search/NicheCombobox";
import { RegionCombobox, type CityItem } from "@/components/search/RegionCombobox";
import { SuggestAxesPanel } from "@/components/search/SuggestAxesPanel";
import type { OfferSource } from "@/components/search/types";
import {
  LEAD_LIMIT_CHOICES,
  getSearches,
  type LeadLimitChoice,
  type PriorTeamSearch,
  type SearchAxisOption,
  type SearchChannel,
  type SearchSummary,
  type UserProfile,
} from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";

/* ── типы состояния формы ─────────────────────────────────────────── */

export const CITY_RADIUS_CHOICES = [0, 10, 25, 50] as const;
export type CityRadiusKm = (typeof CITY_RADIUS_CHOICES)[number];

export interface CityPick {
  name: string;
  country: string | null;
  population: number | null;
  radiusKm: CityRadiusKm;
}

export type WebsiteFilter = "any" | "with" | "without";
export const RATING_CHOICES = [0, 4, 4.5] as const;
export const REVIEWS_CHOICES = [0, 20, 50] as const;

export const EXCLUSION_PRESETS = [
  { key: "chains", labelKey: "search.excl.chains" as const },
  { key: "government", labelKey: "search.excl.government" as const },
  { key: "marketplaces", labelKey: "search.excl.marketplaces" as const },
];

const LANGUAGE_OPTIONS = [
  { code: "uk", labelKey: "search.lang.uk" as const },
  { code: "ru", labelKey: "search.lang.ru" as const },
  { code: "en", labelKey: "search.lang.en" as const },
  { code: "de", labelKey: "search.lang.de" as const },
  { code: "es", labelKey: "search.lang.es" as const },
  { code: "fr", labelKey: "search.lang.fr" as const },
  { code: "pl", labelKey: "search.lang.pl" as const },
];

export interface ComposerProps {
  // 1 — кого
  niche: string;
  onNicheChange: (v: string) => void;
  idealCustomer: string;
  onIdealCustomerChange: (v: string) => void;
  exclusions: string;
  onExclusionsChange: (v: string) => void;
  exclusionPresets: Set<string>;
  onToggleExclusionPreset: (key: string) => void;
  targetLanguages: string[];
  onTargetLanguagesChange: (v: string[]) => void;
  aiTouched: Record<string, number>;
  // 2 — где и сколько
  regionDraft: string;
  onRegionDraftChange: (v: string) => void;
  cities: CityPick[];
  onAddCity: (c: CityPick) => void;
  onRemoveCity: (name: string) => void;
  onCityRadius: (name: string, r: CityRadiusKm) => void;
  leadLimit: LeadLimitChoice;
  onLeadLimitChange: (v: LeadLimitChoice) => void;
  channels: SearchChannel[];
  selectedChannels: Set<string>;
  onToggleChannel: (key: string) => void;
  onAllChannels: () => void;
  repeatWeekly: boolean;
  onToggleRepeatWeekly: () => void;
  // 3 — фильтры и досье
  websiteFilter: WebsiteFilter;
  onWebsiteFilterChange: (v: WebsiteFilter) => void;
  minRating: number;
  onMinRatingChange: (v: number) => void;
  minReviews: number;
  onMinReviewsChange: (v: number) => void;
  findDecisionMakers: boolean;
  onToggleDecisionMakers: () => void;
  offerSource: OfferSource;
  onOfferSourceChange: (v: OfferSource) => void;
  profession: string;
  onProfessionChange: (v: string) => void;
  profile: UserProfile | null;
  // запуск
  tokensBalance: number | null;
  onLaunch: () => void;
  launching: boolean;
  launchDisabled: boolean;
  submitError: string | null;
  duplicates: Record<string, PriorTeamSearch[]>;
  // Henry
  onOpenHenry: () => void;
  axesOptions: SearchAxisOption[] | null;
  axesLoading: boolean;
  axesError: string | null;
  onFetchAxes: () => void;
  onApplyAxis: (opt: SearchAxisOption) => void;
  onDismissAxes: () => void;
  // история
  teamId: string | undefined;
  onRepeat: (niche: string, region: string) => void;
}

/* ── мелкие примитивы ─────────────────────────────────────────────── */

function Chip({
  active,
  onClick,
  children,
  title,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      style={{
        padding: "4px 10px",
        fontSize: 12,
        lineHeight: 1.4,
        borderRadius: 999,
        cursor: "pointer",
        border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
        background: active
          ? "color-mix(in srgb, var(--accent) 12%, transparent)"
          : "var(--surface)",
        color: active ? "var(--accent)" : "var(--text-muted)",
        fontWeight: active ? 600 : 500,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </button>
  );
}

function Segment<T extends string | number>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div
      style={{
        display: "inline-flex",
        border: "1px solid var(--border)",
        borderRadius: 8,
        overflow: "hidden",
        background: "var(--surface)",
      }}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            onClick={() => onChange(o.value)}
            style={{
              padding: "4px 9px",
              fontSize: 11.5,
              border: "none",
              cursor: "pointer",
              background: active ? "var(--accent)" : "transparent",
              color: active ? "var(--accent-fg)" : "var(--text-muted)",
              fontWeight: active ? 600 : 500,
              whiteSpace: "nowrap",
            }}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function Toggle({
  on,
  onClick,
  children,
  hint,
}: {
  on: boolean;
  onClick: () => void;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={hint}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        background: "none",
        border: "none",
        padding: "2px 0",
        cursor: "pointer",
        color: "var(--text)",
        fontSize: 12.5,
        textAlign: "left",
      }}
    >
      <span
        style={{
          width: 30,
          height: 17,
          borderRadius: 9,
          background: on ? "var(--accent)" : "var(--border)",
          position: "relative",
          flexShrink: 0,
          transition: "background 0.15s",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: on ? 15 : 2,
            width: 13,
            height: 13,
            borderRadius: "50%",
            background: "#fff",
            transition: "left 0.15s",
          }}
        />
      </span>
      <span>{children}</span>
    </button>
  );
}

function Label({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div
      className="eyebrow"
      style={{
        fontSize: 10,
        marginBottom: 6,
        display: "flex",
        alignItems: "baseline",
        gap: 6,
      }}
    >
      <span>{children}</span>
      {aside && (
        <span
          style={{
            textTransform: "none",
            letterSpacing: 0,
            fontWeight: 500,
            color: "var(--text-dim)",
          }}
        >
          {aside}
        </span>
      )}
    </div>
  );
}

function Hint({ children }: { children: ReactNode }) {
  return (
    <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 5, lineHeight: 1.45 }}>
      {children}
    </div>
  );
}

function Column({
  step,
  icon,
  title,
  children,
}: {
  step: number;
  icon: IconName;
  title: string;
  children: ReactNode;
}) {
  const style: CSSProperties = {
    padding: "14px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    minWidth: 0,
  };
  return (
    <div className="card" style={style}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          style={{
            width: 24,
            height: 24,
            borderRadius: 8,
            background: "var(--accent-soft)",
            color: "var(--accent)",
            display: "grid",
            placeItems: "center",
            fontSize: 11.5,
            fontWeight: 800,
            flexShrink: 0,
          }}
        >
          {step}
        </span>
        <span style={{ fontSize: 14, fontWeight: 700 }}>{title}</span>
        <Icon name={icon} size={14} style={{ color: "var(--text-dim)", marginLeft: "auto" }} />
      </div>
      {children}
    </div>
  );
}

function useFlash(key: number | undefined) {
  const [cls, setCls] = useState("");
  useEffect(() => {
    if (!key) return;
    setCls("lumen-touched");
    const id = setTimeout(() => setCls(""), 1300);
    return () => clearTimeout(id);
  }, [key]);
  return cls;
}

function formatPopulation(n: number | null): string | null {
  if (!n) return null;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")} млн`;
  if (n >= 1000) return `${Math.round(n / 1000)} тыс.`;
  return String(n);
}

/* ── сам композер ─────────────────────────────────────────────────── */

export function SearchComposer(p: ComposerProps) {
  const { t } = useLocale();
  const nicheFlash = useFlash(p.aiTouched.niche);
  const regionFlash = useFlash(p.aiTouched.region);
  const idealFlash = useFlash(p.aiTouched.ideal_customer);
  const exclFlash = useFlash(p.aiTouched.exclusions);

  const allChannels = p.channels.length > 0 && p.selectedChannels.size === p.channels.length;
  const totalLeads = p.cities.length * p.leadLimit;
  const dmPrice = p.findDecisionMakers ? 1 : 0;
  const tokens = totalLeads * (1 + dmPrice);
  const dupCities = p.cities.filter((c) => (p.duplicates[c.name] ?? []).length > 0);

  const summary = [
    p.niche.trim() || t("search.sum.noNiche"),
    p.cities.length
      ? p.cities
          .map((c) => (c.radiusKm ? `${c.name} +${c.radiusKm} км` : c.name))
          .join(", ")
      : t("search.sum.noCity"),
    p.cities.length > 1 ? `${p.cities.length} × ${p.leadLimit}` : `${p.leadLimit}`,
  ].join(" · ");
  const extras = [
    p.websiteFilter === "with" ? t("search.site.with") : null,
    p.websiteFilter === "without" ? t("search.site.without") : null,
    p.minRating ? t("search.sum.rating", { n: String(p.minRating) }) : null,
    p.minReviews ? t("search.sum.reviews", { n: p.minReviews }) : null,
    p.findDecisionMakers ? t("search.sum.dm") : null,
    p.repeatWeekly ? t("search.sum.weekly") : null,
  ].filter(Boolean) as string[];

  const offerText =
    (p.profile?.service_description ?? p.profile?.profession ?? "").trim();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {p.axesOptions !== null || p.axesLoading || p.axesError ? (
        <SuggestAxesPanel
          profile={p.profile}
          loading={p.axesLoading}
          options={p.axesOptions}
          error={p.axesError}
          onFetch={p.onFetchAxes}
          onApply={p.onApplyAxis}
          onDismiss={p.onDismissAxes}
        />
      ) : null}

      <div className="dob-cols">
        {/* ── 1. Кого ищем ─────────────────────────────────────── */}
        <Column step={1} icon="search" title={t("search.col.who")}>
          <div className={nicheFlash}>
            <Label aside={t("search.required")}>{t("search.form.niche")}</Label>
            <NicheCombobox
              value={p.niche}
              onChange={p.onNicheChange}
              placeholder={t("search.form.nichePh")}
              language={p.profile?.language_code ?? undefined}
            />
          </div>

          <div className={idealFlash}>
            <Label aside={t("search.forAi")}>{t("search.form.ideal")}</Label>
            <textarea
              className="textarea"
              rows={2}
              value={p.idealCustomer}
              onChange={(e) => p.onIdealCustomerChange(e.target.value)}
              placeholder={t("search.form.idealPh")}
              style={{ fontSize: 12.5 }}
            />
          </div>

          <div className={exclFlash}>
            <Label>{t("search.form.exclude")}</Label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
              {EXCLUSION_PRESETS.map((e) => (
                <Chip
                  key={e.key}
                  active={p.exclusionPresets.has(e.key)}
                  onClick={() => p.onToggleExclusionPreset(e.key)}
                >
                  {p.exclusionPresets.has(e.key) && <Icon name="check" size={10} />}{" "}
                  {t(e.labelKey)}
                </Chip>
              ))}
            </div>
            <input
              className="input"
              value={p.exclusions}
              onChange={(e) => p.onExclusionsChange(e.target.value)}
              placeholder={t("search.form.excludePh")}
              style={{ fontSize: 12.5 }}
            />
          </div>

          <div style={{ flex: 1 }} />
          <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
            {t("search.henryHint")}{" "}
            <button type="button" onClick={p.onFetchAxes} style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: "var(--accent-ink)", fontWeight: 600, fontSize: 12 }}>
              {t("search.axes.eyebrow")} →
            </button>
          </div>
        </Column>

        {/* ── 2. Где и сколько ─────────────────────────────────── */}
        <Column step={2} icon="mapPin" title={t("search.col.where")}>
          <div className={regionFlash}>
            <Label aside={t("search.cities.aside")}>{t("search.cities")}</Label>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {p.cities.map((c) => {
                const dups = p.duplicates[c.name] ?? [];
                return (
                  <div key={c.name}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "7px 8px 7px 10px",
                        borderRadius: 10,
                        border: "1px solid " + (dups.length ? "var(--warm)" : "var(--border)"),
                        background: "var(--surface-2)",
                      }}
                    >
                      <Icon name="mapPin" size={13} style={{ color: "var(--accent)", flexShrink: 0 }} />
                      <div style={{ flex: 1, minWidth: 0, fontSize: 12.5 }}>
                        <span style={{ fontWeight: 600 }}>{c.name}</span>
                        <span style={{ color: "var(--text-dim)" }}>
                          {[c.country, formatPopulation(c.population)]
                            .filter(Boolean)
                            .map((x) => ` · ${x}`)
                            .join("")}
                        </span>
                      </div>
                      <Segment
                        value={c.radiusKm}
                        onChange={(r) => p.onCityRadius(c.name, r)}
                        options={CITY_RADIUS_CHOICES.map((r) => ({
                          value: r,
                          label: r === 0 ? t("search.radius.inside") : `+${r}`,
                        }))}
                      />
                      <button
                        type="button"
                        className="btn-icon"
                        onClick={() => p.onRemoveCity(c.name)}
                        style={{ width: 24, height: 24 }}
                        title={t("common.delete")}
                      >
                        <Icon name="x" size={12} />
                      </button>
                    </div>
                    {dups.length > 0 && (
                      <div style={{ fontSize: 11.5, color: "var(--warm)", margin: "4px 0 0 6px" }}>
                        <Icon name="clock" size={11} />{" "}
                        {t("search.dup.line", {
                          who: dups[0].user_name,
                          n: dups[0].leads_count,
                        })}{" "}
                        <Link href={`/app/sessions/${dups[0].search_id}`} style={{ color: "var(--accent)" }}>
                          {t("search.preflight.openSession")}
                        </Link>
                      </div>
                    )}
                  </div>
                );
              })}
              <RegionCombobox
                value={p.regionDraft}
                onChange={p.onRegionDraftChange}
                onPick={(entry: CityItem) =>
                  p.onAddCity({
                    name: entry.name,
                    country: entry.country,
                    population: entry.population,
                    radiusKm: 0,
                  })
                }
                onSubmitFree={(text) =>
                  p.onAddCity({ name: text, country: null, population: null, radiusKm: 0 })
                }
                placeholder={
                  p.cities.length ? t("search.cities.addPh") : t("search.form.regionPh")
                }
                language={p.profile?.language_code ?? undefined}
              />
            </div>
            <Hint>{t("search.cities.help")}</Hint>
          </div>

          <div>
            <Label aside={p.cities.length > 1 ? t("search.perCity") : undefined}>
              {t("search.form.leadCount")}
            </Label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {LEAD_LIMIT_CHOICES.map((n) => (
                <Chip key={n} active={p.leadLimit === n} onClick={() => p.onLeadLimitChange(n)}>
                  {n}
                </Chip>
              ))}
            </div>
            <Hint>{t("search.form.leadCountHint")}</Hint>
          </div>

          <div title={t("search.form.langHelp")}>
            <Label aside={t("search.lang.aside")}>{t("search.form.lang")}</Label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {LANGUAGE_OPTIONS.map((l) => {
                const on = p.targetLanguages.includes(l.code);
                return (
                  <Chip
                    key={l.code}
                    active={on}
                    onClick={() =>
                      p.onTargetLanguagesChange(
                        on
                          ? p.targetLanguages.filter((c) => c !== l.code)
                          : [...p.targetLanguages, l.code],
                      )
                    }
                    title={t(l.labelKey)}
                  >
                    {l.code.toUpperCase()}
                  </Chip>
                );
              })}
            </div>
          </div>
          <div>
            <Label>{t("search.form.channels")}</Label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              <Chip active={allChannels} onClick={p.onAllChannels}>
                {t("search.channels.all")}
              </Chip>
              {p.channels.map((c) => (
                <Chip
                  key={c.key}
                  active={!allChannels && p.selectedChannels.has(c.key)}
                  onClick={() => p.onToggleChannel(c.key)}
                  title={`${c.what} ${c.limit}`}
                >
                  {c.title}
                </Chip>
              ))}
            </div>
          </div>

          <div style={{ flex: 1 }} />
          <Toggle on={p.repeatWeekly} onClick={p.onToggleRepeatWeekly} hint={t("search.weekly.hint")}>
            {t("search.weekly")}
          </Toggle>
        </Column>

        {/* ── 3. Фильтры и досье ───────────────────────────────── */}
        <Column step={3} icon="filter" title={t("search.col.filters")}>
          <div>
            <Label>{t("search.site")}</Label>
            <Segment
              value={p.websiteFilter}
              onChange={p.onWebsiteFilterChange}
              options={[
                { value: "any", label: t("search.site.any") },
                { value: "with", label: t("search.site.with") },
                { value: "without", label: t("search.site.without") },
              ]}
            />
            <Hint>
              {p.websiteFilter === "without"
                ? t("search.site.hintWithout")
                : p.websiteFilter === "with"
                  ? t("search.site.hintWith")
                  : t("search.site.hintAny")}
            </Hint>
          </div>

          <div>
            <Label>{t("search.quality")}</Label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
              <Segment
                value={p.minRating}
                onChange={p.onMinRatingChange}
                options={RATING_CHOICES.map((r) => ({
                  value: r,
                  label: r ? `★ ${r}+` : t("search.quality.any"),
                }))}
              />
              <Segment
                value={p.minReviews}
                onChange={p.onMinReviewsChange}
                options={REVIEWS_CHOICES.map((r) => ({
                  value: r,
                  label: r ? t("search.quality.reviews", { n: r }) : t("search.quality.anyReviews"),
                }))}
              />
            </div>
            <Hint>{t("search.quality.hint")}</Hint>
          </div>

          <div>
            <Label>{t("search.dossier")}</Label>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12.5 }}>
                <Icon name="check" size={13} style={{ color: "var(--accent)" }} />
                {t("search.dossier.base")}
              </div>
              <Toggle on={p.findDecisionMakers} onClick={p.onToggleDecisionMakers} hint={t("search.form.dmHelp")}>
                {t("search.form.dm")}
                <span style={{ color: "var(--text-dim)" }}> · {t("search.dossier.dmPrice")}</span>
              </Toggle>
            </div>
          </div>

          <div>
            <Label>{t("search.offer")}</Label>
            <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
              <Chip active={p.offerSource === "profile"} onClick={() => p.onOfferSourceChange("profile")}>
                {t("search.form.offerSource.profile")}
              </Chip>
              <Chip active={p.offerSource === "custom"} onClick={() => p.onOfferSourceChange("custom")}>
                {t("search.form.offerSource.custom")}
              </Chip>
            </div>
            {p.offerSource === "profile" ? (
              offerText ? (
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--text-muted)",
                    lineHeight: 1.45,
                    display: "-webkit-box",
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                  title={offerText}
                >
                  {offerText}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                  {t("search.form.offerSource.profileEmpty")}{" "}
                  <Link href="/app/profile" style={{ color: "var(--accent)" }}>
                    {t("search.form.offerSource.profileLink")}
                  </Link>
                </div>
              )
            ) : (
              <textarea
                className="textarea"
                rows={2}
                value={p.profession}
                onChange={(e) => p.onProfessionChange(e.target.value)}
                placeholder={t("search.form.offerPh")}
                style={{ fontSize: 12.5 }}
              />
            )}
          </div>
        </Column>
      </div>

      {/* ── строка запуска ───────────────────────────────────────── */}
      <div
        className="card"
        style={{
          padding: "12px 18px",
          display: "flex",
          alignItems: "center",
          gap: 14,
          flexWrap: "wrap",
        }}
      >
        <button
          type="button"
          className={p.launchDisabled || p.launching ? "btn" : "btn m-sheen"}
          disabled={p.launchDisabled}
          onClick={p.onLaunch}
          style={{ padding: "9px 18px", fontSize: 13.5 }}
        >
          <Icon name="search" size={14} />
          {p.launching ? t("common.loading") : t("search.form.launch")}
        </button>
        <div style={{ flex: 1, minWidth: 220, fontSize: 13, lineHeight: 1.4 }}>
          <div style={{ fontWeight: 600 }}>{summary}</div>
          {extras.length > 0 && (
            <div style={{ color: "var(--text-muted)", fontSize: 12 }}>{extras.join(" · ")}</div>
          )}
        </div>
        <div style={{ textAlign: "right", fontSize: 12.5, color: "var(--text-muted)" }}>
          <div>
            <b style={{ color: "var(--text)" }}>{t("search.cost.tokens", { n: tokens })}</b>
            {p.tokensBalance !== null && (
              <span> · {t("search.cost.balance", { n: p.tokensBalance })}</span>
            )}
          </div>
          {dupCities.length > 0 && (
            <div style={{ color: "var(--warm)" }}>
              <Icon name="clock" size={11} />{" "}
              {t("search.dup.short", { cities: dupCities.map((c) => c.name).join(", ") })}
            </div>
          )}
          {p.submitError && <div style={{ color: "var(--cold)" }}>{p.submitError}</div>}
        </div>
      </div>

      <HistoryStrip teamId={p.teamId} onRepeat={p.onRepeat} />
    </div>
  );
}

/* ── история одной строкой ────────────────────────────────────────── */

function HistoryStrip({
  teamId,
  onRepeat,
}: {
  teamId: string | undefined;
  onRepeat: (niche: string, region: string) => void;
}) {
  const { t } = useLocale();
  const [rows, setRows] = useState<SearchSummary[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSearches(teamId ? { teamId } : {})
      .then((list) => !cancelled && setRows(list.filter((r) => !r.archived_at)))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, [teamId]);

  const items = (rows ?? []).slice(0, 6);
  const when = (iso: string): string => {
    const d = new Date(iso);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) return t("dob.today");
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  };
  const stateKey = (r: SearchSummary): TranslationKey | null => {
    if (r.status === "running" || r.status === "pending") return "dob.collecting";
    if (r.status === "failed") return "dob.failed";
    return null;
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", padding: "0 4px" }}>
      <span className="eyebrow" style={{ fontSize: 10 }}>
        {t("dob.history")}
      </span>
      <Link href="/app/sessions" style={{ fontSize: 12, color: "var(--accent-ink)", fontWeight: 600, marginRight: 6 }}>
        {t("search.historyAll")} →
      </Link>
      {rows === null && <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{t("common.loading")}</span>}
      {rows !== null && items.length === 0 && (
        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{t("dob.historyEmpty")}</span>
      )}
      {items.map((r) => {
        const sk = stateKey(r);
        return (
          <span
            key={r.id}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 6px 4px 10px",
              borderRadius: 999,
              border: "1px solid var(--border)",
              background: "var(--surface)",
              fontSize: 12,
            }}
          >
            <Link href={`/app/sessions/${r.id}`} style={{ color: "var(--text)", textDecoration: "none" }}>
              <b style={{ fontWeight: 600 }}>{r.niche}</b> · {r.region}
              <span style={{ color: "var(--text-dim)" }}>
                {" "}
                · {when(r.created_at)} · {sk ? t(sk) : r.leads_count}
                {!sk && r.hot_leads_count ? (
                  <span style={{ color: "var(--hot)" }}> · {r.hot_leads_count} hot</span>
                ) : null}
              </span>
            </Link>
            <button
              type="button"
              className="btn-icon"
              style={{ width: 20, height: 20 }}
              onClick={() => onRepeat(r.niche, r.region)}
              title={t("dob.repeat")}
            >
              <Icon name="rotateCcw" size={11} />
            </button>
          </span>
        );
      })}

    </div>
  );
}

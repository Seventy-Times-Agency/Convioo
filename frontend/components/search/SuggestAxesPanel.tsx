"use client";

import { Icon } from "@/components/Icon";
import { useLocale } from "@/lib/i18n";
import type { SearchAxisOption, UserProfile } from "@/lib/api";

export function SuggestAxesPanel({
  profile,
  loading,
  options,
  error,
  onFetch,
  onApply,
  onDismiss,
}: {
  profile: UserProfile | null;
  loading: boolean;
  options: SearchAxisOption[] | null;
  error: string | null;
  onFetch: () => void;
  onApply: (opt: SearchAxisOption) => void;
  onDismiss: () => void;
}) {
  const { t } = useLocale();

  // Auto-fill is only meaningful when Henry has SOMETHING to base
  // suggestions on. Without a profile signal we'd just be calling
  // the LLM with an empty seed.
  const profileHasSignal = Boolean(
    (profile?.service_description ?? "").trim() ||
      (profile?.profession ?? "").trim() ||
      (profile?.niches ?? []).length > 0 ||
      (profile?.home_region ?? "").trim(),
  );
  if (!profileHasSignal) return null;

  return (
    <div
      style={{
        padding: 14,
        borderRadius: 12,
        border:
          "1px solid color-mix(in srgb, var(--accent) 25%, var(--border))",
        background:
          "linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, var(--surface)), var(--surface))",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
        }}
      >
        <div>
          <div className="eyebrow" style={{ marginBottom: 2 }}>
            {t("search.axes.eyebrow")}
          </div>
          <div
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: 1.5,
            }}
          >
            {t("search.axes.subtitle")}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {options !== null && (
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={onDismiss}
              disabled={loading}
            >
              {t("search.axes.hide")}
            </button>
          )}
          <button
            type="button"
            className="btn btn-sm"
            onClick={onFetch}
            disabled={loading}
          >
            <Icon name="sparkles" size={13} />
            {loading
              ? t("common.loading")
              : options === null
                ? t("search.axes.cta")
                : t("search.axes.ctaAgain")}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ fontSize: 12, color: "var(--cold)" }}>{error}</div>
      )}

      {options !== null && options.length === 0 && !loading && (
        <div
          style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}
        >
          {t("search.axes.empty")}
        </div>
      )}

      {options !== null && options.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 8,
          }}
        >
          {options.map((opt, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onApply(opt)}
              style={{
                textAlign: "left",
                padding: 12,
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 10,
                cursor: "pointer",
                display: "flex",
                flexDirection: "column",
                gap: 4,
              }}
            >
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  letterSpacing: "-0.005em",
                }}
              >
                {opt.niche}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-muted)",
                }}
              >
                {opt.region}
              </div>
              {opt.rationale && (
                <div
                  style={{
                    fontSize: 11.5,
                    color: "var(--text-dim)",
                    lineHeight: 1.4,
                    marginTop: 4,
                  }}
                >
                  {opt.rationale}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

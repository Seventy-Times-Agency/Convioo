"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  type Branding,
  getBranding,
  updateBranding,
} from "@/lib/api";
import { activeTeamId } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showSuccess } from "@/lib/toast";

/**
 * Wave 4 — white-label branding settings.
 *
 * Agency name + accent colour + logo are stamped onto every public
 * client report. The branding is team-scoped, so we resolve the
 * active team from the workspace selector (the same value the sidebar
 * and CRM read). Editing is owner-only: the backend returns 403 for
 * non-owners, which we surface inline.
 */

const MAX_LOGO_BYTES = 200 * 1024;
const HEX_RE = /^#[0-9a-fA-F]{6}$/;

/** Rough byte size of a base64 data URL payload (no atob needed). */
function dataUrlByteLength(dataUrl: string): number {
  const comma = dataUrl.indexOf(",");
  const b64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
  const padding = b64.endsWith("==") ? 2 : b64.endsWith("=") ? 1 : 0;
  return Math.floor((b64.length * 3) / 4) - padding;
}

export function BrandingSection() {
  const { t } = useLocale();
  const fileRef = useRef<HTMLInputElement | null>(null);

  const [teamId, setTeamId] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [color, setColor] = useState("");
  const [logo, setLogo] = useState<string | null>(null);

  useEffect(() => {
    setTeamId(activeTeamId());
  }, []);

  useEffect(() => {
    if (!teamId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(false);
    getBranding(teamId)
      .then((b) => {
        if (cancelled) return;
        setName(b.brand_name ?? "");
        setColor(b.brand_color ?? "");
        setLogo(b.brand_logo ?? null);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [teamId]);

  const onPickLogo = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFieldError(null);
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = typeof reader.result === "string" ? reader.result : "";
      if (!dataUrl.startsWith("data:image/")) {
        setFieldError(t("settings.branding.logo.errorType"));
        return;
      }
      if (dataUrlByteLength(dataUrl) > MAX_LOGO_BYTES) {
        setFieldError(t("settings.branding.logo.errorSize"));
        return;
      }
      setLogo(dataUrl);
    };
    reader.onerror = () => setFieldError(t("settings.branding.logo.errorRead"));
    reader.readAsDataURL(file);
  };

  const clearLogo = () => {
    setLogo(null);
    setFieldError(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const save = async () => {
    if (!teamId) return;
    setFieldError(null);
    const trimmedColor = color.trim();
    if (trimmedColor && !HEX_RE.test(trimmedColor)) {
      setFieldError(t("settings.branding.color.errorFormat"));
      return;
    }
    setSaving(true);
    setForbidden(false);
    try {
      const updated: Branding = await updateBranding(teamId, {
        brand_name: name.trim() || null,
        brand_color: trimmedColor || null,
        brand_logo: logo,
      });
      setName(updated.brand_name ?? "");
      setColor(updated.brand_color ?? "");
      setLogo(updated.brand_logo ?? null);
      showSuccess(t("common.saved"));
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setForbidden(true);
      } else {
        setFieldError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        {t("settings.branding.eyebrow")}
      </div>
      <div
        style={{
          fontSize: 13,
          color: "var(--text-muted)",
          lineHeight: 1.5,
          marginBottom: 18,
        }}
      >
        {t("settings.branding.help")}
      </div>

      {loading ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {t("common.loading")}
        </div>
      ) : !teamId ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5 }}>
          {t("settings.branding.noTeam")}
        </div>
      ) : loadError ? (
        <div style={{ fontSize: 13, color: "var(--cold)" }}>
          {t("settings.branding.error")}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* ---- Agency name ---- */}
          <div>
            <label
              className="eyebrow"
              style={{ display: "block", marginBottom: 6 }}
            >
              {t("settings.branding.name.label")}
            </label>
            <input
              type="text"
              className="input"
              value={name}
              maxLength={120}
              placeholder={t("settings.branding.name.placeholder")}
              onChange={(e) => setName(e.target.value)}
              style={{ width: "100%", maxWidth: 420 }}
            />
          </div>

          {/* ---- Accent colour ---- */}
          <div>
            <label
              className="eyebrow"
              style={{ display: "block", marginBottom: 6 }}
            >
              {t("settings.branding.color.label")}
            </label>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <input
                type="color"
                aria-label={t("settings.branding.color.label")}
                value={HEX_RE.test(color.trim()) ? color.trim() : "#6366F1"}
                onChange={(e) => setColor(e.target.value.toUpperCase())}
                style={{
                  width: 40,
                  height: 36,
                  padding: 2,
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  background: "var(--surface-2)",
                  cursor: "pointer",
                }}
              />
              <input
                type="text"
                className="input"
                value={color}
                placeholder="#6366F1"
                spellCheck={false}
                onChange={(e) => setColor(e.target.value)}
                style={{ width: 140, fontFamily: "var(--font-jetbrains)" }}
              />
            </div>
          </div>

          {/* ---- Logo ---- */}
          <div>
            <label
              className="eyebrow"
              style={{ display: "block", marginBottom: 6 }}
            >
              {t("settings.branding.logo.label")}
            </label>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 14,
                flexWrap: "wrap",
              }}
            >
              <div
                style={{
                  width: 88,
                  height: 88,
                  borderRadius: 12,
                  border: "1px solid var(--border)",
                  background: "var(--surface-2)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  overflow: "hidden",
                  flexShrink: 0,
                }}
              >
                {logo ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={logo}
                    alt={t("settings.branding.logo.previewAlt")}
                    style={{
                      maxWidth: "100%",
                      maxHeight: "100%",
                      objectFit: "contain",
                    }}
                  />
                ) : (
                  <Icon name="briefcase" size={22} />
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/png,image/jpeg,image/jpg,image/webp"
                  onChange={onPickLogo}
                  style={{ fontSize: 12.5 }}
                />
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <span
                    style={{ fontSize: 12, color: "var(--text-muted)" }}
                  >
                    {t("settings.branding.logo.hint")}
                  </span>
                  {logo && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={clearLogo}
                    >
                      {t("settings.branding.logo.remove")}
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {forbidden && (
            <div
              style={{
                padding: 12,
                borderRadius: 10,
                background: "color-mix(in srgb, var(--cold) 8%, transparent)",
                border:
                  "1px solid color-mix(in srgb, var(--cold) 25%, var(--border))",
                fontSize: 13,
                lineHeight: 1.5,
                color: "var(--text-muted)",
              }}
            >
              {t("settings.branding.forbidden")}
            </div>
          )}

          {fieldError && (
            <div style={{ fontSize: 13, color: "var(--cold)", lineHeight: 1.5 }}>
              {fieldError}
            </div>
          )}

          <div>
            <button
              type="button"
              className="btn"
              disabled={saving}
              onClick={save}
            >
              {saving ? t("common.saving") : t("common.save")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

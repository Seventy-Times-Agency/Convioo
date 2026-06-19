"use client";

import type { EmailStatus } from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";

/**
 * Small colored pill summarizing a lead's email verification state.
 *
 *  valid   → green  "Verified"
 *  risky   → amber  "Risky"
 *  invalid → red    "Invalid"
 *  unknown → gray   "Unverified"  (also the null fallback)
 *
 * Colors map onto the shared theme tokens used elsewhere for lead
 * temperature (--hot / --warm / --cold) so the pill reads consistently
 * in light and dark mode.
 */

type Tone = { color: string; labelKey: TranslationKey };

const TONES: Record<EmailStatus, Tone> = {
  valid: { color: "var(--hot)", labelKey: "lead.email.status.valid" },
  risky: { color: "var(--warm)", labelKey: "lead.email.status.risky" },
  invalid: { color: "var(--cold)", labelKey: "lead.email.status.invalid" },
  unknown: { color: "var(--text-dim)", labelKey: "lead.email.status.unknown" },
};

export function EmailStatusBadge({
  status,
  size = "md",
}: {
  status: EmailStatus | null | undefined;
  size?: "sm" | "md";
}) {
  const { t } = useLocale();
  const tone = TONES[status ?? "unknown"] ?? TONES.unknown;
  const fontSize = size === "sm" ? 10 : 11;
  const pad = size === "sm" ? "1px 6px" : "2px 8px";
  return (
    <span
      title={t("lead.email.status.title")}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        fontSize,
        fontWeight: 600,
        lineHeight: 1.4,
        padding: pad,
        borderRadius: 999,
        whiteSpace: "nowrap",
        color: tone.color,
        background: `color-mix(in srgb, ${tone.color} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${tone.color} 30%, transparent)`,
      }}
    >
      <span
        aria-hidden
        style={{
          width: 6,
          height: 6,
          borderRadius: 999,
          background: tone.color,
          flexShrink: 0,
        }}
      />
      {t(tone.labelKey)}
    </span>
  );
}

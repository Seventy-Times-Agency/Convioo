"use client";

import { useState } from "react";

/**
 * Convioo brand component.
 *
 * Reads ``/convioo-logo.png`` from the public folder for the full
 * wordmark; if missing or in compact mode, falls back to a teal-on-
 * navy "C" mark next to the text. Drop the logo into
 * ``frontend/public/convioo-logo.png`` (transparent PNG works best)
 * and the wordmark renders automatically.
 */
export const CONVIOO_LOGO_URL = "/convioo-logo.png";

const TEAL = "#10B5B0";
const NAVY = "#1F3D5C";

export function ConviooMark({ size }: { size: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: Math.max(6, Math.round(size * 0.25)),
        background: `linear-gradient(135deg, ${TEAL}, ${NAVY})`,
        display: "grid",
        placeItems: "center",
        color: "white",
        fontSize: Math.round(size * 0.5),
        fontWeight: 800,
        letterSpacing: "-0.02em",
        flexShrink: 0,
      }}
    >
      C
    </div>
  );
}

export function ConviooWordmark({
  height = 28,
  fallbackTextSize = 16,
}: {
  height?: number;
  fallbackTextSize?: number;
}) {
  const [broken, setBroken] = useState(false);
  if (broken || !CONVIOO_LOGO_URL) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <ConviooMark size={Math.round(height * 0.85)} />
        <span
          style={{
            fontWeight: 700,
            fontSize: fallbackTextSize,
            letterSpacing: "-0.015em",
            color: NAVY,
          }}
        >
          Convioo
        </span>
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={CONVIOO_LOGO_URL}
      alt="Convioo"
      onError={() => setBroken(true)}
      style={{ height, width: "auto", display: "block" }}
    />
  );
}

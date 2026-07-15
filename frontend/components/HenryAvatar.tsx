"use client";

import { useState } from "react";

/**
 * Avatar shown for the consultant across the app.
 *
 * Reads ``/henry.jpg`` from the public folder; if that 404s the
 * gradient-initials fallback renders so the page never looks broken
 * while the photo is still being uploaded.
 */
export const HENRY_AVATAR_URL = "/henry.jpg";

export function HenryAvatar({
  size,
  ring,
}: {
  size: number;
  ring?: boolean;
}) {
  const [broken, setBroken] = useState(false);
  const ringStyle = ring
    ? {
        boxShadow: "0 0 0 2px var(--surface), 0 0 0 4px var(--accent)",
      }
    : undefined;
  if (broken || !HENRY_AVATAR_URL) {
    return (
      <div
        style={{
          width: size,
          height: size,
          borderRadius: "50%",
          background: "var(--gradient3)",
          display: "grid",
          placeItems: "center",
          color: "white",
          fontSize: Math.round(size * 0.42),
          fontWeight: 700,
          letterSpacing: "-0.02em",
          flexShrink: 0,
          ...ringStyle,
        }}
      >
        H
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={HENRY_AVATAR_URL}
      alt="Henry"
      width={size}
      height={size}
      onError={() => setBroken(true)}
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        objectFit: "cover",
        flexShrink: 0,
        ...ringStyle,
      }}
    />
  );
}

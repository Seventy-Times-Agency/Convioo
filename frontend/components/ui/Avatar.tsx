"use client";

import type { CSSProperties } from "react";

/**
 * Кружок участника: картинка, если загружена, иначе инициалы на
 * цветной подложке. Размер задаётся числом, чтобы одна и та же
 * вёрстка работала в таблице (28) и в шапке профиля (56).
 */
export function Avatar({
  src,
  initials,
  color,
  size = 32,
  style,
}: {
  src?: string | null;
  initials: string;
  color?: string;
  size?: number;
  style?: CSSProperties;
}) {
  const base: CSSProperties = {
    width: size,
    height: size,
    borderRadius: "50%",
    flexShrink: 0,
    overflow: "hidden",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: Math.round(size * 0.38),
    fontWeight: 700,
    background: color ?? "var(--accent)",
    color: "var(--accent-fg)",
    ...style,
  };
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={src} alt="" style={{ ...base, objectFit: "cover" }} />
    );
  }
  return <span style={base}>{initials}</span>;
}

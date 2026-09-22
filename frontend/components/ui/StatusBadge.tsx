"use client";

import type { HTMLAttributes } from "react";
import { TAG_COLOR_HEX, type TagColor } from "@/lib/api";

export interface StatusBadgeProps
  extends Omit<HTMLAttributes<HTMLSpanElement>, "color"> {
  label: string;
  /** Palette colour name from the team's status palette (slate,
   * green, amber, …) or a raw #RRGGBB value. */
  color?: string | null;
}

function resolveHex(color: string | null | undefined): string {
  if (!color) return TAG_COLOR_HEX.slate;
  if (color.startsWith("#")) return color;
  return TAG_COLOR_HEX[color as TagColor] ?? TAG_COLOR_HEX.slate;
}

/** Lead-status pill: tinted dot + label rendered from the team's
 * palette. One component for tables, cards and the kanban board. */
export function StatusBadge({ label, color, style, ...rest }: StatusBadgeProps) {
  const hex = resolveHex(color);
  return (
    <span
      className="chip"
      style={{ color: "var(--text-muted)", ...style }}
      {...rest}
    >
      <span
        aria-hidden
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: hex,
          display: "inline-block",
        }}
      />
      {label}
    </span>
  );
}

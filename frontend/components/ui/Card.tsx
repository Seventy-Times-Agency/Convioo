"use client";

import type { HTMLAttributes, ReactNode } from "react";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Adds hover lift for clickable cards. */
  interactive?: boolean;
  /** Overrides the default card padding (px). */
  padding?: number;
  children?: ReactNode;
}

/** White surface on the warm background — the etalon's base block. */
export function Card({
  interactive,
  padding,
  className,
  style,
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={["card", interactive ? "card-hover" : "", className ?? ""]
        .filter(Boolean)
        .join(" ")}
      style={padding !== undefined ? { padding, ...style } : style}
      {...rest}
    >
      {children}
    </div>
  );
}

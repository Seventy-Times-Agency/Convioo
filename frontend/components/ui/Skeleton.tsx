"use client";

import type { CSSProperties } from "react";

export interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  circle?: boolean;
  style?: CSSProperties;
  className?: string;
}

/** Shimmering placeholder block. */
export function Skeleton({
  width = "100%",
  height = 12,
  circle,
  style,
  className,
}: SkeletonProps) {
  return (
    <div
      aria-hidden
      className={["skeleton", circle ? "skeleton-circle" : "", className ?? ""]
        .filter(Boolean)
        .join(" ")}
      style={{ width, height, ...style }}
    />
  );
}

/** N stacked text lines — the default list/card loading state. */
export function SkeletonLines({
  lines = 3,
  gap = 10,
}: {
  lines?: number;
  gap?: number;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap }}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} width={`${100 - i * 12}%`} />
      ))}
    </div>
  );
}

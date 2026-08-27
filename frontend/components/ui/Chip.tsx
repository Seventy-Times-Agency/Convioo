"use client";

import type { HTMLAttributes, ReactNode } from "react";

export type ChipTone = "default" | "accent" | "positive" | "attention" | "problem";

const TONE_CLASS: Record<ChipTone, string> = {
  default: "chip",
  accent: "chip chip-accent",
  positive: "chip chip-hot",
  attention: "chip chip-warm",
  problem: "chip chip-cold",
};

export interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: ChipTone;
  children?: ReactNode;
}

/** Pill chip in the etalon's single colour language:
 * green = positive, amber = attention, red = problem. */
export function Chip({ tone = "default", className, children, ...rest }: ChipProps) {
  return (
    <span
      className={[TONE_CLASS[tone], className ?? ""].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </span>
  );
}

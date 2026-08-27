"use client";

import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "soft" | "icon";
type Size = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style. `primary` is the single main action of a screen —
   * one per screen per the style guide. */
  variant?: Variant;
  size?: Size;
  /** Shows a subtle busy state and disables the button. */
  loading?: boolean;
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: "btn",
  ghost: "btn btn-ghost",
  soft: "btn btn-soft",
  icon: "btn-icon",
};

const SIZE_CLASS: Record<Size, string> = {
  sm: "btn-sm",
  md: "",
  lg: "btn-lg",
};

/** Etalon button. Green solid = main action; ghost = secondary;
 * soft = tertiary/inline; icon = square icon-only. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { variant = "primary", size = "md", loading, className, children, disabled, ...rest },
    ref,
  ) {
    const cls = [
      VARIANT_CLASS[variant],
      variant === "icon" ? "" : SIZE_CLASS[size],
      className ?? "",
    ]
      .filter(Boolean)
      .join(" ");
    return (
      <button
        ref={ref}
        type={rest.type ?? "button"}
        className={cls}
        disabled={disabled || loading}
        {...rest}
      >
        {loading ? "…" : children}
      </button>
    );
  },
);

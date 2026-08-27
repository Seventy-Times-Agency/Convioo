"use client";

import type { ReactNode } from "react";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: ReactNode;
  /** One or two sentences that teach what this screen is for and
   * what to do first — "пустой экран учит". */
  hint?: ReactNode;
  /** The single main action, if the viewer's role can act. */
  action?: ReactNode;
}

/** Teaching empty state per the etalon: what this is, what to do,
 * one action. */
export function EmptyState({ icon, title, hint, action }: EmptyStateProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        gap: 10,
        padding: "48px 24px",
      }}
    >
      {icon != null && (
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 12,
            background: "var(--accent-soft)",
            color: "var(--accent)",
            display: "grid",
            placeItems: "center",
          }}
        >
          {icon}
        </div>
      )}
      <div style={{ fontSize: 15.5, fontWeight: 700 }}>{title}</div>
      {hint != null && (
        <div
          style={{
            fontSize: 13.5,
            color: "var(--text-muted)",
            lineHeight: 1.55,
            maxWidth: 420,
          }}
        >
          {hint}
        </div>
      )}
      {action != null && <div style={{ marginTop: 6 }}>{action}</div>}
    </div>
  );
}

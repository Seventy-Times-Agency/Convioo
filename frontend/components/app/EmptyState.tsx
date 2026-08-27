"use client";

import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";
import { Icon, type IconName } from "@/components/Icon";

export interface EmptyStateAction {
  label: string;
  href?: string;
  onClick?: () => void;
  variant?: "primary" | "ghost";
}

export interface EmptyStateProps {
  icon?: IconName;
  title: string;
  body?: string;
  actions?: EmptyStateAction[];
  children?: ReactNode;
  style?: CSSProperties;
}

const wrapperStyle: CSSProperties = {
  padding: "48px 28px",
  textAlign: "center",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 14,
};

export function EmptyState({
  icon = "sparkles",
  title,
  body,
  actions,
  children,
  style,
}: EmptyStateProps) {
  return (
    <div className="card" style={{ ...wrapperStyle, ...style }}>
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: 14,
          background:
            "color-mix(in srgb, var(--accent) 12%, var(--surface-2))",
          color: "var(--accent)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Icon name={icon} size={26} />
      </div>
      <div
        style={{
          fontSize: 18,
          fontWeight: 600,
          letterSpacing: "-0.01em",
          color: "var(--text)",
        }}
      >
        {title}
      </div>
      {body && (
        <div
          style={{
            fontSize: 13.5,
            color: "var(--text-muted)",
            lineHeight: 1.55,
            maxWidth: 440,
          }}
        >
          {body}
        </div>
      )}
      {children}
      {actions && actions.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: 10,
            flexWrap: "wrap",
            justifyContent: "center",
            marginTop: 4,
          }}
        >
          {actions.map((a, i) => {
            const cls =
              a.variant === "ghost" ? "btn btn-ghost" : "btn";
            if (a.href) {
              return (
                <Link key={i} href={a.href} className={cls}>
                  {a.label}
                </Link>
              );
            }
            return (
              <button
                key={i}
                type="button"
                className={cls}
                onClick={a.onClick}
              >
                {a.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

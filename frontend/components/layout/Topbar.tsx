"use client";

import { Fragment, type ReactNode } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

interface Crumb {
  label: string;
  href?: string;
}

interface TopbarProps {
  title?: string;
  subtitle?: string;
  crumbs?: Crumb[];
  right?: ReactNode;
}

export function Topbar({ title, subtitle, crumbs, right }: TopbarProps) {
  return (
    <div className="topbar">
      <div style={{ display: "flex", alignItems: "center", gap: 14, minWidth: 0 }}>
        {crumbs ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 13,
              color: "var(--text-muted)",
            }}
          >
            {crumbs.map((c, i) => (
              <Fragment key={`${c.label}-${i}`}>
                {i > 0 && <Icon name="chevronRight" size={14} />}
                {c.href ? (
                  <Link href={c.href} style={{ color: "inherit" }}>
                    {c.label}
                  </Link>
                ) : (
                  <span style={{ color: "var(--text)" }}>{c.label}</span>
                )}
              </Fragment>
            ))}
          </div>
        ) : (
          <div>
            {title && (
              <div style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-0.01em" }}>
                {title}
              </div>
            )}
            {subtitle && (
              <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 2 }}>
                {subtitle}
              </div>
            )}
          </div>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {right}
        <LanguageSwitcher compact />
      </div>
    </div>
  );
}

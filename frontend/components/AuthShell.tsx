"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { ConviooMark } from "@/components/ConviooLogo";
import { useLocale } from "@/lib/i18n";

export function AuthShell({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const { t } = useLocale();
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        background: "var(--bg)",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          padding: "40px 56px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
          }}
        >
          <Link
            href="/"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              fontWeight: 700,
              fontSize: 15,
              color: "inherit",
              textDecoration: "none",
            }}
          >
            <ConviooMark size={28} />
            <span>Convioo</span>
          </Link>
          <LanguageSwitcher compact />
        </div>
        <div style={{ flex: 1, display: "flex", alignItems: "center" }}>
          <div style={{ width: "100%", maxWidth: 400 }}>
            <h1
              style={{
                fontSize: 44,
                fontWeight: 700,
                letterSpacing: "-0.03em",
                lineHeight: 1.02,
                margin: "0 0 12px",
              }}
            >
              {title}
            </h1>
            {children}
          </div>
        </div>
        <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
          © 2026 Convioo
        </div>
      </div>

      <div
        style={{
          position: "relative",
          overflow: "hidden",
          background: "var(--surface)",
          borderLeft: "1px solid var(--border)",
        }}
      >
        <div className="mesh-bg">
          <div className="blob3" />
        </div>
        <div
          style={{
            position: "absolute",
            inset: 0,
            padding: 56,
            display: "flex",
            flexDirection: "column",
            justifyContent: "flex-end",
          }}
        >
          <div className="eyebrow" style={{ marginBottom: 16 }}>
            {t("auth.inside.eyebrow")}
          </div>
          <div
            style={{
              fontSize: 30,
              fontWeight: 600,
              letterSpacing: "-0.02em",
              lineHeight: 1.15,
              color: "var(--text)",
              maxWidth: 380,
            }}
          >
            {t("auth.inside.body")}
          </div>
          <div
            style={{
              display: "flex",
              gap: 14,
              marginTop: 32,
              color: "var(--text-muted)",
              fontSize: 13,
            }}
          >
            {t("auth.inside.tags")}
          </div>
        </div>
      </div>
    </div>
  );
}

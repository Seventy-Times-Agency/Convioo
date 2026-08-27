"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { ConviooWordmark } from "@/components/ConviooLogo";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useLocale } from "@/lib/i18n";

/**
 * Minimal page chrome reused by /privacy, /terms and /cookies. Keeps
 * the legal copy readable on its own while mirroring the landing
 * page's branding header.
 */
export function LegalShell({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  const { t } = useLocale();
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg)",
        color: "var(--text)",
      }}
    >
      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 50,
          background: "color-mix(in srgb, var(--bg) 85%, transparent)",
          backdropFilter: "blur(14px)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div
          style={{
            maxWidth: 880,
            margin: "0 auto",
            padding: "16px 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Link
            href="/"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 10,
              textDecoration: "none",
            }}
          >
            <ConviooWordmark height={22} fallbackTextSize={14} />
          </Link>
          <LanguageSwitcher />
        </div>
      </div>

      <div
        style={{
          maxWidth: 760,
          margin: "0 auto",
          padding: "48px 24px 80px",
          fontSize: 15,
          lineHeight: 1.7,
        }}
      >
        <div
          style={{
            fontSize: 12,
            color: "var(--text-dim)",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            marginBottom: 8,
          }}
        >
          {t("legal.updated", { date: updated })}
        </div>
        <h1
          style={{
            fontSize: 36,
            fontWeight: 800,
            letterSpacing: "-0.02em",
            margin: "0 0 24px",
          }}
        >
          {title}
        </h1>
        <article className="legal-body">{children}</article>

        <div
          style={{
            marginTop: 56,
            paddingTop: 24,
            borderTop: "1px solid var(--border)",
            display: "flex",
            gap: 18,
            flexWrap: "wrap",
            fontSize: 13,
            color: "var(--text-muted)",
          }}
        >
          <Link href="/privacy" style={{ color: "inherit" }}>
            {t("legal.nav.privacy")}
          </Link>
          <Link href="/terms" style={{ color: "inherit" }}>
            {t("legal.nav.terms")}
          </Link>
          <Link href="/cookies" style={{ color: "inherit" }}>
            {t("legal.nav.cookies")}
          </Link>
          <span style={{ marginLeft: "auto" }}>
            {t("legal.nav.contact", { email: "support@convioo.com" })}
          </span>
        </div>
      </div>
    </div>
  );
}

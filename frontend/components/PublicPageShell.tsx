"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { ConviooWordmark } from "@/components/ConviooLogo";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useLocale } from "@/lib/i18n";

/**
 * Shared wrapper for marketing pages outside the app dashboard
 * (pricing, help center, changelog, vs/<competitor>). Keeps the
 * landing page's sticky branded header and a small footer with the
 * legal links so visitors always have an exit door.
 */
export function PublicPageShell({
  children,
  width = 960,
}: {
  children: ReactNode;
  width?: number;
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
            maxWidth: 1280,
            margin: "0 auto",
            padding: "16px 32px",
            display: "flex",
            alignItems: "center",
            gap: 28,
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
          <nav
            style={{
              display: "flex",
              gap: 18,
              fontSize: 13,
              color: "var(--text-muted)",
            }}
          >
            <Link href="/pricing" style={{ color: "inherit" }}>
              {t("public.nav.pricing")}
            </Link>
            <Link href="/help" style={{ color: "inherit" }}>
              {t("public.nav.help")}
            </Link>
            <Link href="/changelog" style={{ color: "inherit" }}>
              {t("public.nav.changelog")}
            </Link>
          </nav>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
            <LanguageSwitcher />
            <Link href="/login" className="btn btn-ghost btn-sm">
              {t("public.nav.signIn")}
            </Link>
            <Link href="/register" className="btn btn-sm">
              {t("public.nav.start")}
            </Link>
          </div>
        </div>
      </div>

      <div
        style={{
          maxWidth: width,
          margin: "0 auto",
          padding: "48px 24px 64px",
        }}
      >
        {children}
      </div>

      <footer
        style={{
          padding: "24px 32px 40px",
          borderTop: "1px solid var(--border)",
          display: "flex",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 12,
          fontSize: 12.5,
          color: "var(--text-dim)",
        }}
      >
        <div>{t("landing.footer.built")}</div>
        <div style={{ display: "flex", gap: 18 }}>
          <Link href="/privacy" style={{ color: "inherit" }}>
            {t("legal.nav.privacy")}
          </Link>
          <Link href="/terms" style={{ color: "inherit" }}>
            {t("legal.nav.terms")}
          </Link>
          <Link href="/cookies" style={{ color: "inherit" }}>
            {t("legal.nav.cookies")}
          </Link>
        </div>
      </footer>
    </div>
  );
}

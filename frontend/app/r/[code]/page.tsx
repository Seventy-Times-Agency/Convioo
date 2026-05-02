"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

import { REFERRAL_COOKIE_NAME } from "@/lib/api";

/**
 * Public referral landing — sets the affiliate cookie + redirects to
 * /register. Server-side attribution happens later when the user
 * submits the registration form (the form forwards the cookie value
 * as ``referral_code`` in the body).
 *
 * Cookie lives 30 days so a visit-now-sign-up-later flow still
 * attributes correctly.
 */
export default function ReferralLanding() {
  const params = useParams<{ code: string }>();
  const router = useRouter();

  useEffect(() => {
    const code = String(params?.code ?? "").trim().toLowerCase();
    if (typeof document !== "undefined" && code) {
      const maxAge = 30 * 24 * 60 * 60;
      document.cookie = `${REFERRAL_COOKIE_NAME}=${encodeURIComponent(code)}; path=/; max-age=${maxAge}; SameSite=Lax`;
    }
    router.replace("/register");
  }, [params, router]);

  return (
    <div
      style={{
        minHeight: "60vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--text-muted)",
        fontSize: 14,
      }}
    >
      Перенаправляем…
    </div>
  );
}

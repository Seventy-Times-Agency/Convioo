"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { ApiError, verifyEmail } from "@/lib/api";
import { getCurrentUser, setCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";

type Status = "pending" | "ok" | "error";

export default function VerifyEmailPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const { t } = useLocale();
  const [status, setStatus] = useState<Status>("pending");
  const [detail, setDetail] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    verifyEmail(params.token)
      .then((authUser) => {
        if (cancelled) return;
        const local = getCurrentUser();
        // If the verifier was already signed in, refresh local
        // state with the fresh email_verified flag. Otherwise we
        // intentionally don't auto-login — the user opens the link
        // from email and proves ownership; they still log in
        // normally.
        if (local && local.user_id === authUser.user_id) {
          setCurrentUser({
            ...local,
            email: authUser.email,
            email_verified: true,
            onboarded: authUser.onboarded,
          });
        }
        setStatus("ok");
      })
      .catch((e) => {
        if (cancelled) return;
        setStatus("error");
        setDetail(
          e instanceof ApiError
            ? e.message
            : e instanceof Error
              ? e.message
              : String(e),
        );
      });
    return () => {
      cancelled = true;
    };
  }, [params.token]);

  return (
    <AuthShell title={t(`verify.${status}.title`)}>
      <div style={{ color: "var(--text-muted)", fontSize: 14.5, lineHeight: 1.55, marginBottom: 22 }}>
        {status === "pending" && t("verify.pending.body")}
        {status === "ok" && t("verify.ok.body")}
        {status === "error" && (detail || t("verify.error.body"))}
      </div>
      {status !== "pending" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {status === "ok" && (
            <button
              type="button"
              className="btn btn-lg"
              onClick={() => router.push("/app")}
              style={{ justifyContent: "center" }}
            >
              {t("verify.ok.continue")} <Icon name="arrow" size={15} />
            </button>
          )}
          <Link
            href="/login"
            className="btn btn-ghost btn-lg"
            style={{ justifyContent: "center" }}
          >
            {t("verify.gotoLogin")}
          </Link>
        </div>
      )}
    </AuthShell>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import { ApiError, verifyEmail } from "@/lib/api";
import { getCurrentUser, setCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";

type Status = "idle" | "verifying" | "ok" | "error";

export default function VerifyEmailPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const { t } = useLocale();
  const [status, setStatus] = useState<Status>("idle");
  const [detail, setDetail] = useState<string | null>(null);

  // No automatic verify on mount: email scanners (Gmail, Outlook)
  // pre-fetch links and would burn the token before the user clicks.
  // Verification only fires on explicit button press.
  const verify = async () => {
    setStatus("verifying");
    setDetail(null);
    try {
      const authUser = await verifyEmail(params.token);
      const local = getCurrentUser();
      if (local && local.user_id === authUser.user_id) {
        setCurrentUser({
          ...local,
          email: authUser.email,
          email_verified: true,
          onboarded: authUser.onboarded,
        });
      }
      setStatus("ok");
    } catch (e) {
      setStatus("error");
      setDetail(
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e),
      );
    }
  };

  // If the user is already logged in AND their email is already
  // verified, this page is just a leftover link — bounce them home.
  useEffect(() => {
    const u = getCurrentUser();
    if (u?.email_verified) router.replace("/app");
  }, [router]);

  return (
    <AuthShell title={t(`verify.${status}.title`)}>
      <div
        style={{
          color: "var(--text-muted)",
          fontSize: 14.5,
          lineHeight: 1.55,
          marginBottom: 22,
        }}
      >
        {status === "idle" && t("verify.idle.body")}
        {status === "verifying" && t("verify.pending.body")}
        {status === "ok" && t("verify.ok.body")}
        {status === "error" && (detail || t("verify.error.body"))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {status === "idle" && (
          <button
            type="button"
            className="btn btn-lg"
            onClick={verify}
            style={{ justifyContent: "center" }}
          >
            {t("verify.idle.cta")} <Icon name="check" size={15} />
          </button>
        )}

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

        {status === "error" && (
          <button
            type="button"
            className="btn btn-lg"
            onClick={verify}
            style={{ justifyContent: "center" }}
          >
            {t("verify.error.retry")} <Icon name="arrow" size={15} />
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
    </AuthShell>
  );
}
